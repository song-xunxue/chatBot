# Matt Pocock Skills 新项目开发流程指南

本文件为全局技能指南，由 Claude Code 在项目初始化时自动复制到项目的 `.claude/` 目录下。

---

## 已安装的全局 Skill 命令

| 命令 | 用途 |
|------|------|
| `/setup-matt-pocock-skills` | 初始化项目配置（Issue tracker、标签、文档布局） |
| `/grill-with-docs` | 需求对齐 + 自动构建术语表（CONTEXT.md）+ ADR |
| `/diagnose` | 系统化调试：复现→假设→验证→修复→回归测试 |
| `/tdd` | 红绿重构循环开发，每次一个垂直切片 |
| `/improve-codebase-architecture` | 扫描架构问题，提出"加深模块"重构建议 |
| `/zoom-out` | 给出模块关系地图，快速理解陌生代码 |
| `/prototype` | 快速构建可抛弃原型验证设计思路 |
| `/to-prd` | 将对话上下文合成 PRD（需先 setup） |
| `/to-issues` | 将 PRD 拆成垂直切片 Issue（需先 setup） |
| `/grill-me` | 纯需求讨论追问（grill-with-docs 简化版） |
| `/caveman` | 超压缩回复模式，省 75% token |
| `/git-guardrails-claude-code` | 拦截危险 git 命令（push/reset --hard 等） |
| `/setup-pre-commit` | 配置 Husky + lint-staged 提交检查 |

---

## Phase 1：项目初始化

```
新项目目录/
  │
  ▼
git init + 初始提交
  │
  ▼
（可选）/setup-matt-pocock-skills
  → Issue tracker: Local markdown
  → Triage labels: 默认
  → Domain docs: Single-context
```

如果不用任务管理功能（/to-prd、/to-issues），这步可以跳过。

---

## Phase 2：需求对齐（最重要，每次做新功能前都跑）

```
/grill-with-docs
```

跟 Agent 说你要做什么，它会逐个追问直到每个细节都理清。过程中自动产出：
- `CONTEXT.md` — 术语表，后续对话 Agent 自动参考
- `docs/adr/` — 关键架构决策记录

**举例：**
```
你：/grill-with-docs
你：我想做一个中文文本分析工具，支持分词和关键词提取

Agent：你说的"分词"是指什么粒度？jieba 粗粒度还是细粒度？
你：默认粗粒度，用户可以切换

Agent：关键词提取用什么算法？TF-IDF？TextRank？还是调大模型？
你：调大模型，支持多个模型切换
```

追问持续到每个分支都清晰。这一步做好，后面基本不会返工。

---

## Phase 3：快速验证（可选）

设计不确定时先出原型再决定：
```
/prototype
你：我想试试两种不同的前端布局方案
```
验证完就删掉，不进代码库。确定的方案记到 `docs/adr/`。

---

## Phase 4：开发实现

### 场景 A：写新功能
```
/tdd
你：实现用户注册登录功能
```
循环：写一个失败测试 → 最少代码通过 → 下一个测试 → 全通过后重构

### 场景 B：调试 Bug
```
/diagnose
你：上传大文件时 500 报错
```
循环：建反馈回路 → 复现 → 假设 → 验证 → 修复 → 回归测试

### 场景 C：看不懂某块代码
```
/zoom-out
你：看不懂 llm_service.py 的调用链
```

### 场景 D：设计不确定想试错
```
/prototype
你：不确定用 FAISS 还是 Chroma 做向量存储
```

---

## Phase 5：定期维护

每隔几天或完成一个大功能后：
```
/improve-codebase-architecture
```
Agent 扫描代码库，找出浅模块和耦合问题，提出重构建议。

---

## 完整流程图

```
新项目
  │
  ├─ git init
  ├─ （可选）/setup-matt-pocock-skills
  │
  ▼
每个功能/改动前
  │
  ├─ /grill-with-docs              ← 对齐需求 + 建术语表
  │     │
  │     ├─ 设计不确定？
  │     │   └─ /prototype          ← 快速验证，用完即删
  │     │
  │     ▼
  ├─ /tdd                          ← TDD 循环实现
  │     │
  │     ├─ 遇到 bug → /diagnose
  │     ├─ 看不懂代码 → /zoom-out
  │     │
  │     ▼
  ├─ 功能完成
  │
  ▼
定期（每几天 / 每个大功能后）
  │
  └─ /improve-codebase-architecture   ← 检查架构健康度
```

---

## 核心

每次动手前先 `/grill-with-docs`，动手时用 `/tdd`，出问题用 `/diagnose`，定期 `/improve-codebase-architecture`。
