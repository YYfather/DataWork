# Git Basics

## Overview

Git is a distributed version control system for tracking changes in source code. It is essential for collaborative development and project management.

## Core Concepts

### Repository (Repo)
- **Definition**: A directory containing your project files and Git history
- **Types**: Local (on your computer) and Remote (on GitHub/GitLab)

### Commit
- **Definition**: A snapshot of your changes at a specific point in time
- **Components**: Message, author, timestamp, parent commit(s)
- **Best practices**: Write clear, descriptive messages

### Branch
- **Definition**: A parallel version of your code
- **Main branch**: `main` or `master` (production code)
- **Feature branches**: For developing new features

### Remote
- **Definition**: A version of your repository hosted on a server
- **Common remotes**: `origin` (your fork), `upstream` (original repo)

## Basic Commands

### Setup
```bash
# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Initialize a new repository
git init

# Clone an existing repository
git clone https://github.com/username/repo.git
```

### Daily Workflow
```bash
# Check status
git status

# Add files to staging
git add filename.txt      # Add specific file
git add .                 # Add all changes

# Commit changes
git commit -m "Description of changes"

# Push to remote
git push origin main

# Pull latest changes
git pull origin main
```

### Branching
```bash
# Create and switch to new branch
git checkout -b feature-name

# Switch between branches
git checkout main
git checkout feature-name

# List branches
git branch

# Merge branch into main
git checkout main
git merge feature-name

# Delete branch
git branch -d feature-name
```

## GitHub Workflow

### 1. Fork & Clone
```bash
# Fork repository on GitHub
# Clone your fork
git clone https://github.com/YOUR_USERNAME/repo.git
cd repo

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/repo.git
```

### 2. Keep Updated
```bash
# Fetch upstream changes
git fetch upstream

# Merge upstream changes
git checkout main
git merge upstream/main
```

### 3. Create Pull Request
```bash
# Create feature branch
git checkout -b feature-name

# Make changes and commit
git add .
git commit -m "Add feature"

# Push to your fork
git push origin feature-name

# Create Pull Request on GitHub
```

## Common Scenarios

### Undo Last Commit
```bash
# Keep changes in working directory
git reset --soft HEAD~1

# Discard changes
git reset --hard HEAD~1
```

### View History
```bash
# View commit history
git log
git log --oneline
git log --graph

# View changes in a commit
git show commit-hash
```

### Stash Changes
```bash
# Save changes temporarily
git stash

# Restore stashed changes
git stash pop
```

## Best Practices

### Commit Messages
- Use present tense ("Add feature" not "Added feature")
- Keep first line under 50 characters
- Add detailed description if needed

### Branching Strategy
- Use descriptive branch names (e.g., `fix-login-bug`, `add-search-feature`)
- Keep branches short-lived
- Merge frequently to avoid conflicts

### Code Review
- Always review before merging
- Use Pull Requests for collaboration
- Address review comments promptly

## Related Topics
- [[SunScan-Data-Analysis]]
- [[Python-for-Science]]
