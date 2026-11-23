FROM docker:29-cli@sha256:34507eb5069d8be82c95dd3b6987d4250fd5fee49b82e2509b7d7a7030740d6d
RUN apk add --no-cache curl
RUN curl -fsSL https://github.com/aquasecurity/trivy/releases/download/v0.76.2/trivy_0.76.2_Linux-64bit.tar.gz -o /tmp/trivy.tgz && echo 'bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf  /tmp/trivy.tgz' | sha256sum -c - && tar xzf /tmp/trivy.tgz -C /usr/local/bin trivy && rm /tmp/trivy.tgz
ENTRYPOINT ["trivy"]
