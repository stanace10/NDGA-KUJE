FROM postgres:16-alpine

RUN apk add --no-cache pgbouncer gettext su-exec
COPY pgbouncer.ini.template /etc/pgbouncer/pgbouncer.ini.template
COPY entrypoint.sh /usr/local/bin/ndga-pgbouncer-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/ndga-pgbouncer-entrypoint && chmod +x /usr/local/bin/ndga-pgbouncer-entrypoint

ENTRYPOINT ["/usr/local/bin/ndga-pgbouncer-entrypoint"]
