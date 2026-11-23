FROM postgres:17-alpine@sha256:526f86d93c6ea08fd3f1fe5605650cacc781b2c6013169a0ad8f42c7d3d84f32
COPY start.sh /usr/local/bin/bc3-start
ENTRYPOINT ["sh","/usr/local/bin/bc3-start"]
CMD ["postgres","-c","ssl=on","-c","ssl_cert_file=/var/lib/postgresql/tls/server.crt","-c","ssl_key_file=/var/lib/postgresql/tls/server.key"]
