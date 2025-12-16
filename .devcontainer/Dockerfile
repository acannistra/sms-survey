# Start from a robust base image, e.g., a common Node or Python image
# For simplicity, we'll use a basic Ubuntu image
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# [1] Install Twilio CLI
# Uses the recommended 'apt' method for Debian/Ubuntu
RUN sudo apt-get update && \
    sudo apt-get install -y wget && \
    wget -qO- https://twilio-cli-prod.s3.amazonaws.com/twilio_pub.asc | sudo apt-key add - && \
    echo 'deb https://twilio-cli-prod.s3.amazonaws.com/apt/ /' | sudo tee /etc/apt/sources.list.d/twilio.list && \
    sudo apt-get update && \
    sudo apt-get install -y twilio && \
    twilio version

# [2] Install Flyctl
# Uses the recommended curl/bash install script
RUN curl -L https://install.fly.io | sh && \
    fly version

# Ensure flyctl is in a globally accessible path.
# The install script typically places it in $HOME/.fly/bin/
# We symlink it for general user access.
# NOTE: The flyctl installer should handle this, but it's a safeguard.
RUN if [ -f /root/.fly/bin/fly ]; then \
        sudo ln -s /root/.fly/bin/fly /usr/local/bin/fly; \
    fi

# [3] Install Claude Code
# Uses the recommended curl/bash native install script
RUN curl -fsSL https://claude.ai/install.sh | bash && \
    claude version

# Set the default shell and user for the container
# This is usually inherited from the base image but good to ensure
# USER vscode
# SHELL ["/bin/bash", "-c"]