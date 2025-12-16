# Start from a robust base image
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# --- Ensure Network Utilities and Install Dependencies ---
RUN apt-get update && \
    # Install essential networking tools like curl, wget, and dnsutils (for debugging/stability)
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl \
        wget \
        dnsutils \
        sudo && \
    rm -rf /var/lib/apt/lists/*

# [1] Install Twilio CLI (This section was stable)
RUN apt-get update && \
    # NOTE: apt-key is deprecated, but used here to stick close to official Twilio install guide
    wget -qO- https://twilio-cli-prod.s3.amazonaws.com/twilio_pub.asc | apt-key add - && \
    echo 'deb https://twilio-cli-prod.s3.amazonaws.com/apt/ /' | tee /etc/apt/sources.list.d/twilio.list && \
    apt-get update && \
    apt-get install -y twilio && \
    twilio version

# [2] Install Flyctl (Using the correct script, but ensuring PATH visibility)
RUN curl -L https://fly.io/install.sh | sh
# Fix 1: Add the installation path to the global environment for the default user ('vscode')
# The script installs to /root/.fly/bin/fly
RUN export PATH="/root/.fly/bin:$PATH" && \
    # Fix 2: Symlink the binary to a globally accessible directory
    sudo ln -s /root/.fly/bin/fly /usr/local/bin/flyctl && \
    flyctl version

# [3] Install Claude Code
# Uses the recommended curl/bash native install script, which places it in /root/.claude/bin
RUN curl -fsSL https://claude.ai/install.sh | bash && \
    # Add the installation directory to the PATH for the rest of this RUN command
    export PATH="/root/.claude/bin:$PATH" && \
    claude version

# Final step: Ensure Claude CLI is globally accessible
RUN sudo ln -s /root/.claude/bin/claude /usr/local/bin/claude
