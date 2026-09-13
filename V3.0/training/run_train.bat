@echo off
rem 清浔 LoRA 训练入口(阶段 C)
rem 用法: run_train.bat smoke                      —— 冒烟(dummy 数据 10 步)
rem       run_train.bat v0 <sft.jsonl路径...>       —— 正式训练(可多个 glob)
rem       run_train.bat v1 xxx.jsonl --model 8b     —— 8B(须先关语音启动器)
setlocal
set HF_HOME=D:\llmtrain-cache
set HF_ENDPOINT=https://hf-mirror.com
set PY=C:\Users\26904\anaconda3\envs\llmtrain\python.exe
set SCRIPT=%~dp0train_sft.py

if "%1"=="smoke" (
  "%PY%" "%SCRIPT%" --smoke
) else (
  "%PY%" "%SCRIPT%" --tag %1 %2 %3 %4 %5
)
endlocal
