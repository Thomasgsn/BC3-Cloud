FROM docker:29-cli@sha256:34507eb5069d8be82c95dd3b6987d4250fd5fee49b82e2509b7d7a7030740d6d
RUN apk add --no-cache bash curl unzip python3 openssl
RUN curl -fsSL https://github.com/kubernetes-sigs/kind/releases/download/v0.32.0/kind-linux-amd64 -o /usr/local/bin/kind && echo '50030de23cf40a18505f20426f6a8506bedf13c6e509244bd1fa9463721b0f54  /usr/local/bin/kind' | sha256sum -c - && chmod +x /usr/local/bin/kind
RUN curl -fsSL https://dl.k8s.io/release/v1.36.1/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl && curl -fsSL https://dl.k8s.io/release/v1.36.1/bin/linux/amd64/kubectl.sha256 -o /tmp/kubectl.sha && echo "$(cat /tmp/kubectl.sha)  /usr/local/bin/kubectl" | sha256sum -c - && chmod +x /usr/local/bin/kubectl
RUN curl -fsSL https://releases.hashicorp.com/terraform/1.17.2/terraform_1.17.2_linux_amd64.zip -o /tmp/terraform.zip && curl -fsSL https://releases.hashicorp.com/terraform/1.17.2/terraform_1.17.2_SHA256SUMS -o /tmp/terraform.sums && cd /tmp && awk '$2 == "terraform_1.17.2_linux_amd64.zip" {print $1 "  terraform.zip"}' terraform.sums | sha256sum -c - && unzip terraform.zip -d /usr/local/bin && rm terraform.zip
WORKDIR /workspace
ENTRYPOINT ["bash"]
