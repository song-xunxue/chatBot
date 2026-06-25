#!/usr/bin/env bash
# MyChat 客户端 - 一键连接云服务器试用（Git Bash）
# 作者: 李文煜  日期: 2026-06-24
# 用法: bash client/run_cloud.sh   （含 access_token，已 gitignore）
export CLIENT_SERVER_URL=http://43.140.219.99:8000
export CLIENT_WS_URL=ws://43.140.219.99:8000/ws
export ACCESS_TOKEN=1bd86c187a76d738f023b8f9680d7525
cd "$(dirname "$0")"
C:/Users/26904/anaconda3/envs/mychat/python.exe app/main.py
