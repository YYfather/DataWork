---
title: Git 基础
description: 分布式版本控制、仓库管理、分支协作与常用 Git 工作流。
category: 学习文档
order: 20
lang: zh
---
# Git 基础

## 概述

Git 是一个分布式版本控制系统，用于追踪源代码的变更。它是协作开发和项目管理的重要工具。

## 核心概念

### 仓库（Repository）
- **定义**：包含项目文件和 Git 历史记录的目录
- **类型**：本地（计算机上）和远程（GitHub/GitLab 上）

### 提交（Commit）
- **定义**：在特定时间点对变更的快照
- **组成部分**：提交信息、作者、时间戳、父提交
- **最佳实践**：编写清晰、描述性的提交信息

### 分支（Branch）
- **定义**：代码的并行版本
- **主分支**：`main` 或 `master`（生产代码）
- **功能分支**：用于开发新功能

### 远程仓库（Remote）
- **定义**：托管在服务器上的仓库版本
- **常见远程仓库**：`origin`（你的 Fork）、`upstream`（原始仓库）

## 基本命令

### 设置
```bash
# 配置 Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 初始化新仓库
git init

# 克隆已有仓库
git clone https://github.com/username/repo.git
```

### 日常工作流
```bash
# 查看状态
git status

# 添加文件到暂存区
git add filename.txt      # 添加指定文件
git add .                 # 添加所有更改

# 提交更改
git commit -m "变更说明"

# 推送到远程
git push origin main

# 拉取最新变更
git pull origin main
```

### 分支操作
```bash
# 创建并切换到新分支
git checkout -b feature-name

# 切换分支
git checkout main
git checkout feature-name

# 列出分支
git branch

# 合并分支到 main
git checkout main
git merge feature-name

# 删除分支
git branch -d feature-name
```

## GitHub 工作流

### 1. Fork 与克隆
```bash
# 在 GitHub 上 Fork 仓库
# 克隆你的 Fork
git clone https://github.com/YOUR_USERNAME/repo.git
cd repo

# 添加上游远程仓库
git remote add upstream https://github.com/ORIGINAL_OWNER/repo.git
```

### 2. 保持更新
```bash
# 获取上游变更
git fetch upstream

# 合并上游变更
git checkout main
git merge upstream/main
```

### 3. 创建 Pull Request
```bash
# 创建功能分支
git checkout -b feature-name

# 做修改并提交
git add .
git commit -m "添加功能"

# 推送到你的 Fork
git push origin feature-name

# 在 GitHub 上创建 Pull Request
```

## 常见场景

### 撤销上一次提交
```bash
# 保留工作目录中的更改
git reset --soft HEAD~1

# 丢弃更改
git reset --hard HEAD~1
```

### 查看历史
```bash
# 查看提交历史
git log
git log --oneline
git log --graph

# 查看某次提交的更改
git show commit-hash
```

### 暂存更改
```bash
# 临时保存更改
git stash

# 恢复暂存的更改
git stash pop
```

## 最佳实践

### 提交信息
- 使用现在时态（"添加功能"而非"添加了功能"）
- 第一行保持在 50 个字符以内
- 如需详细说明可在后续行补充

### 分支策略
- 使用描述性分支名称（例如 `fix-login-bug`、`add-search-feature`）
- 保持分支短生命周期
- 频繁合并以避免冲突

### 代码审查
- 合并前务必进行审查
- 使用 Pull Request 进行协作
- 及时处理审查意见

## 相关主题
- [[SunScan-Data-Analysis]]
- [[Python-for-Science]]
