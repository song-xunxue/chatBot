"""
清浔人设 LoRA 训练脚本(阶段 C,2026-09-12)
Unsloth QLoRA SFT:读 server 数据导出管线的 alpaca JSONL,把人设微调进 Qwen3 参数。

用法(llmtrain conda 环境):
  python train_sft.py --data ../server/data/training/qingxun_sft_*.jsonl --model 4b
  python train_sft.py --smoke          # 冒烟:内置 dummy 数据跑 10 步验证环境
产物:./outputs/qingxun-lora-vN/ (adapter,safetensors,几百 MB,永久存档可回滚)

设计依据(docs/04 调研报告):LoRA rank 32-64(缓解低秩机械感)、通用数据 0-30% 配比
(单角色数据防过拟合)、学习率 5e-6 起(RoCIT 参照)、序列 2048 内(4060 显存约束)。

作者: 李文煜
日期: 2026-09-12
"""
import argparse
import glob
import json
import sys
from pathlib import Path

# —— 数据集构造(纯函数,冒烟与正式共用)——

DUMMY_SAMPLES = [
    {"instruction": "在吗", "input": "", "output": "嗯嗯在的~夫君找我什么事呀",
     "system": "你是清浔,温柔的女友系角色,说话自然像微信聊天,绝不用句号结尾。", "history": []},
    {"instruction": "今天好累啊", "input": "", "output": "辛苦啦~要不要跟我说说,我陪着你",
     "system": "你是清浔,温柔的女友系角色,说话自然像微信聊天,绝不用句号结尾。", "history": []},
    {"instruction": "晚上吃什么", "input": "", "output": "想吃火锅~上次那家怎么样呀",
     "system": "你是清浔,温柔的女友系角色,说话自然像微信聊天,绝不用句号结尾。",
     "history": [["早上好", "早上好呀~今天也要元气满满"]]},
]


def load_alpaca(paths: list[str]) -> list[dict]:
    """读一个或多个 alpaca JSONL(支持 glob),合并成样本列表"""
    out = []
    for p in paths:
        for f in glob.glob(p):
            for line in Path(f).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("instruction") and d.get("output"):
                    out.append(d)
    if not out:
        sys.exit(f"未读到任何样本: {paths}")
    return out


def to_sharegpt(samples: list[dict]) -> list[dict]:
    """alpaca(system/instruction/history/output)→ sharegpt 多轮格式"""
    rows = []
    for s in samples:
        convs = []
        if s.get("system"):
            convs.append({"from": "system", "value": s["system"]})
        for u, a in s.get("history", []):
            convs.append({"from": "human", "value": u})
            convs.append({"from": "gpt", "value": a})
        convs.append({"from": "human", "value": s["instruction"]})
        convs.append({"from": "gpt", "value": s["output"]})
        rows.append({"conversations": convs})
    return rows


_ROLE_MAP = {"system": "system", "human": "user", "gpt": "assistant"}


def rows_to_text(rows: list[dict], tokenizer) -> list[dict]:
    """sharegpt → {"text": 套 chat template 后的完整对话文本}。
    enable_thinking=False:Qwen3 模板关思考段(训练目标不混 <think> 脚手架)。"""
    texts = []
    for r in rows:
        msgs = [{"role": _ROLE_MAP[c["from"]], "content": c["value"]}
                for c in r["conversations"]]
        texts.append({"text": tokenizer.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=False, enable_thinking=False)})
    return texts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="*", default=[], help="alpaca JSONL 路径(支持 glob)")
    ap.add_argument("--model", default="4b", choices=["4b", "8b"], help="基座档位(4060 8GB:4b 稳/8b 贴极限须关语音)")
    ap.add_argument("--smoke", action="store_true", help="冒烟模式:dummy 数据 10 步")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--lr", type=float, default=5e-6)
    ap.add_argument("--lora-rank", type=int, default=32)
    ap.add_argument("--tag", default="", help="版本标签(如 v0/v1,产物目录后缀)")
    ap.add_argument("--max-len", type=int, default=2048)
    args = ap.parse_args()

    from unsloth import FastLanguageModel  # 延迟导入(冒烟前的参数/数据检查不用等)

    model_ids = {
        "4b": "unsloth/Qwen3-4B-unsloth-bnb-4bit",     # 预量化 4bit(~3GB 下载)
        "8b": "unsloth/Qwen3-8B-unsloth-bnb-4bit",
    }
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_ids[args.model], max_seq_length=args.max_len, load_in_4bit=True)

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_rank,                                   # rank 32:缓解低秩机械感(调研报告 §3.4)
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=args.lora_rank * 2,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",              # unsloth 检查点:省显存关键
    )

    samples = DUMMY_SAMPLES if args.smoke else load_alpaca(args.data)
    rows = to_sharegpt(samples)
    print(f"样本数: {len(rows)}(model={args.model}, rank={args.lora_rank}, "
          f"epochs={args.epochs}, lr={args.lr}, smoke={args.smoke})")

    from datasets import Dataset
    ds = Dataset.from_list(rows_to_text(rows, tokenizer))    # 手动套 chat template 出 text 列

    from trl import SFTConfig, SFTTrainer
    tag = args.tag or ("smoke" if args.smoke else "v0")
    out_dir = str(Path(__file__).parent / "outputs" / f"qingxun-lora-{tag}")
    cfg = SFTConfig(
        output_dir=out_dir,
        per_device_train_batch_size=1,                     # 4060 显存约束
        gradient_accumulation_steps=8,
        num_train_epochs=1 if args.smoke else args.epochs,
        max_steps=10 if args.smoke else -1,
        learning_rate=args.lr,
        logging_steps=1 if args.smoke else 5,
        save_strategy="no" if args.smoke else "epoch",
        optim="paged_adamw_8bit",                          # 4060 实测 +25% 吞吐(arXiv 2509.12229)
        bf16=True,                                          # unsloth 4bit 底座为 bf16,强制 bf16(fp16 会 TypeError)
        fp16=False,
        report_to="none",
        seed=42,
        dataset_text_field="text",                          # 预套模板的 text 列(见 rows_to_text)
        max_length=args.max_len,
        packing=False,
    )
    trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=ds, args=cfg)
    trainer.train()

    model.save_pretrained(out_dir)                         # adapter(safetensors,永久存档)
    tokenizer.save_pretrained(out_dir)
    print(f"训练完成,adapter 已存: {out_dir}")
    print("下一步:ollama 部署可用 unsloth 的 GGUF 导出或 merge 后量化(见 README)")


if __name__ == "__main__":
    main()
