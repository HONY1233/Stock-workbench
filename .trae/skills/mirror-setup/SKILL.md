---
name: "mirror-setup"
description: "Configure domestic mirror sources for pip, npm, git, cargo, conda, go. Invoke when user needs to speed up downloads, set up mirrors, or mentions 'mirror', '镜像', 'mirror source', 'mirror setup', '加速下载', '国内源'."
---

# Mirror Source Setup (镜像源配置)

Global skill for configuring Chinese domestic mirror sources across multiple package managers and tools. Speeds up downloads when the default registries are slow or inaccessible.

## How To Use

When you need to configure mirrors, the AI assistant will:

1. **Detect the environment** (pip / npm / git / cargo / conda / go)
2. **Generate and run the appropriate configuration commands**
3. **Verify the configuration** is working

## Supported Mirror Sources

### pip (Python)
```bash
# Tianjing University (TUNA)
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# Or Aliyun
pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# Or USTC
pip config set global.index-url https://mirrors.ustc.edu.cn/pypi/web/simple/
```

### npm (Node.js)
```bash
# npmmirror (recommended)
npm config set registry https://registry.npmmirror.com

# Verify
npm config get registry
```

### git clone (GitHub mirror)
```bash
# Method 1: Use kgithub (no account needed)
git clone https://kgithub.com/user/repo.git

# Method 2: Use ghproxy (proxy service)
git clone https://ghproxy.com/https://github.com/user/repo.git

# Method 3: Use gitclone.com
git clone https://gitclone.com/github.com/user/repo.git

# Method 4: Set up git config for automatic redirect
git config --global url."https://ghproxy.com/https://github.com/".insteadOf "https://github.com/"
```

### cargo (Rust)
```bash
# Create config if not exists
mkdir -p ~/.cargo

# Set TUNA mirror
cat >> ~/.cargo/config.toml << 'EOF'
[source.crates-io]
replace-with = "tuna"

[source.tuna]
registry = "https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"
EOF
```

### conda (Anaconda)
```bash
# TUNA mirror
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/
conda config --set show_channel_urls yes
```

### go (Golang)
```bash
# GOPROXY
go env -w GOPROXY=https://goproxy.cn,direct
go env -w GO111MODULE=on
```

## One-Click Setup Script

A PowerShell script `setup.ps1` is available in the mirror-setup repository that configures all mirrors at once.
