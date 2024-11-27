ARG vault_version=${VAULT_VERSION:-latest}
FROM hashicorp/vault:${vault_version}

RUN apk update && apk upgrade && apk add bash jq openssl curl mysql-client mariadb-connector-c

ENV VAULT_ADDR="http://127.0.0.1:8200"

USER vault

VOLUME /tmp/shared

ENTRYPOINT ["/bin/bash"]
