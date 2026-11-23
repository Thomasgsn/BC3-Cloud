FROM alpine:3.23@sha256:469c9ea410b9215eaee7976ba6c0639039b444be8e5d638f7abbada189971eb2
RUN apk add --no-cache stunnel
COPY stunnel.conf /etc/stunnel/stunnel.conf
USER 10001
ENTRYPOINT ["stunnel","/etc/stunnel/stunnel.conf"]
