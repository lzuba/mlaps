#!/bin/bash

set -x
mkdir -p /tmp/shared
export VAULT_ADDR=http://127.0.0.1:8200

vault server -dev -dev-listen-address 0.0.0.0:8200 &

while ! vault status; do
  echo "Vault is not running"
  sleep 1s
done

if [ ! -f "/tmp/shared/INITIALIZED" ]; then
    echo "Initializing Vault!"

    vault login token=dev
    vault secrets enable transit
    vault auth enable approle
    vault write -f transit/keys/client-passwords
    vault write auth/approle/role/client-passwords \
      secret_id_ttl=3h \
      token_num_uses=10 \
      token_ttl=1h \
      token_max_ttl=3h \
      secret_id_num_uses=0 \
      token_policies=client_passwords

    vault policy write client_passwords - < /policy.hcl

    vault secrets enable pki
    vault secrets tune -max-lease-ttl=87600h pki

    # Generate the CA expires in 10y
    vault write pki/roles/mlaps \
      allow_any_name=true \
      allow_subdomains=true \
      allow_wildcard_certificates=false \
      enforce_hostnames=true \
      server_flag=false \
      client_flag=true \
      code_signing_flag=false \
      email_protection_flag=false \
      use_csr_common_name=false \
      organization="$CERT_COMPANYNAME" \
      ou="MLAPS" \
      country='["$CERT_COUNTRY"]' \
      locality='["$CERT_LOCALITY"]' \
      province='["$CERT_PROVINCE"]' \
      max_ttl=43800h \
      ttl=43800h \
      key_bits=2048

    vault write -field=certificate pki/root/generate/internal \
      common_name="com.$YOURCOMPANY.mlaps" \
      ttl=45600h \
      key_bits=4096 > /tmp/shared/ca.crt

    openssl req -nodes -newkey rsa:2048 -keyout /tmp/shared/web.key -out /tmp/shared/web.csr \
        -subj "/C=$CERT_COUNTRY/ST=$CERT_PROVINCE/L=$CERT_LOCALITY/O=$CERT_COMPANYNAME/OU=MLAPS/CN=mlaps.$YOURCOMPANY.com"

    # get a server certificate
    vault write -field=certificate pki/sign/mlaps common_name="mlaps.$YOURCOMPANY.com" csr=@/tmp/shared/web.csr ttl=8808h > /tmp/shared/web.crt

    ROLE_ID=$(vault read -format=json auth/approle/role/client-passwords/role-id | jq .data.role_id)
    SECRET_ID=$(vault write -format=json -f auth/approle/role/client-passwords/secret-id  | jq .data.secret_id)
    while ! mysql -u dev -h db -pdev dev -e "SHOW TABLES;"; do
      echo "Waiting for DB to be reachable"
      sleep 1s
    done

    mysql -u dev -h db -pdev dev -e "insert into auth_secret (role_id,secret_id) values ($ROLE_ID, $SECRET_ID);"

    touch /tmp/shared/INITIALIZED

    #https://stackoverflow.com/questions/28251144/inserting-and-selecting-uuids-as-binary16
    #mysql -u dev -h db -pdev dev -e "insert into machine (id, hostname, serialnumber, enroll_time, enroll_success, disabled) values (UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),\"myHostname\",\"T35T1N600M86\",\"2020-01-01 12:12:12.121212\",True,False);"
    
    #mysql -u dev -h db -pdev dev -e "insert into Machine (id, hostname, serialnumber, enroll_time, enroll_success, disabled) values (91a5de62-c27b-11ed-b06e-73a6e07e676e,'myDifferentHostname','T35T1N600M87',2020-01-01 13:13:13.131313,True,False);"
    #mysql -u dev -h db -pdev dev -e "insert into Machine (id, hostname, serialnumber, enroll_time, enroll_success, disabled) values (a0bae91a-c27b-11ed-97d2-efbae491e385,'myVeryDifferentHostname','T35T1N600M88',2020-01-01 14:14:14.141414,True,False);"
    #mysql -u dev -h db -pdev dev -e "insert into Password (id, machine_id, password, status, password_set, password_received, password_expiry) values (d2de2708-c27c-11ed-8b81-4b498eb56a2e,81a70234-c27b-11ed-a0f5-fb79d6671c6e,'MyEncryptedPassword1','Testing',False,2020-01-01 12:24:24.242424,2020-01-01 12:36:36.363636);"
    #mysql -u dev -h db -pdev dev -e "insert into Password (id, machine_id, password, status, password_set, password_received, password_expiry) values (dbf70378-c27c-11ed-ac0a-ff5d046c5f60,81a70234-c27b-11ed-a0f5-fb79d6671c6e,'MyEncryptedPassword2','Testing',False,2020-01-01 12:36:36.363636,2020-01-01 13:00:00.000000);"
    #mysql -u dev -h db -pdev dev -e "insert into Password (id, machine_id, password, status, password_set, password_received, password_expiry) values (e8359956-c27c-11ed-afb3-c3922f844a02,91a5de62-c27b-11ed-b06e-73a6e07e676e,'MyEncryptedPassword3','Testing',False,2020-01-01 13:26:26.262626,2020-01-01 13:39:39.393939);"
    #mysql -u dev -h db -pdev dev -e "insert into Password (id, machine_id, password, status, password_set, password_received, password_expiry) values (f04fa1fe-c27c-11ed-bdb5-8fd286cb2228,91a5de62-c27b-11ed-b06e-73a6e07e676e,'MyEncryptedPassword4','Testing',False,2020-01-01 13:39:39.393939,2020-01-01 14:00:00.000000);"
    #mysql -u dev -h db -pdev dev -e "insert into Password (id, machine_id, password, status, password_set, password_received, password_expiry) values (f5b92d0e-c27c-11ed-8728-77b6c3364352,a0bae91a-c27b-11ed-97d2-efbae491e385,'MyEncryptedPassword5','Testing',False,2020-01-01 14:28:28.282828,2020-01-01 14:42:42.424242);"
    #mysql -u dev -h db -pdev dev -e "insert into Password (id, machine_id, password, status, password_set, password_received, password_expiry) values (fa5a818c-c27c-11ed-a703-d75f772b0c57,a0bae91a-c27b-11ed-97d2-efbae491e385,'MyEncryptedPassword6','Testing',False,2020-01-01 14:42:42.424242,2020-01-01 15:00:00.000000);"
    #mysql -u dev -h db -pdev dev -e "insert into Checkin (id, uuid, mid, checkin_time) values (1,d2de2708-c27c-11ed-8b81-4b498eb56a2e,d2de2708-c27c-11ed-8b81-4b498eb56a2e,2020-01-01 12:13:12.121212);"
    #mysql -u dev -h db -pdev dev -e "insert into Checkin (id, uuid, mid, checkin_time) values (2,dbf70378-c27c-11ed-ac0a-ff5d046c5f60,dbf70378-c27c-11ed-ac0a-ff5d046c5f60,2020-01-01 12:25:24.242424);"
    #mysql -u dev -h db -pdev dev -e "insert into Checkin (id, uuid, mid, checkin_time) values (3,e8359956-c27c-11ed-afb3-c3922f844a02,e8359956-c27c-11ed-afb3-c3922f844a02,2020-01-01 13:14:13.131313);"
    #mysql -u dev -h db -pdev dev -e "insert into Checkin (id, uuid, mid, checkin_time) values (4,f04fa1fe-c27c-11ed-bdb5-8fd286cb2228,f04fa1fe-c27c-11ed-bdb5-8fd286cb2228,2020-01-01 13:27:26.262626);"
    #mysql -u dev -h db -pdev dev -e "insert into Checkin (id, uuid, mid, checkin_time) values (5,f5b92d0e-c27c-11ed-8728-77b6c3364352,f5b92d0e-c27c-11ed-8728-77b6c3364352,2020-01-01 14:15:14.141414);"
    #mysql -u dev -h db -pdev dev -e "insert into Checkin (id, uuid, mid, checkin_time) values (6,fa5a818c-c27c-11ed-a703-d75f772b0c57,fa5a818c-c27c-11ed-a703-d75f772b0c57,2020-01-01 14:29:28.282828);"
    #mysql -u dev -h db -pdev dev -e "insert into AccessLog (id, admin_kurzel, getTime, machine_id, password_id) values (1,'big-admin',2020-01-01 12:24:24.242424,81a70234-c27b-11ed-a0f5-fb79d6671c6e,d2de2708-c27c-11ed-8b81-4b498eb56a2e);"
    #mysql -u dev -h db -pdev dev -e "insert into AccessLog (id, admin_kurzel, getTime, machine_id, password_id) values (2,'big-admin',2020-01-01 13:26:26.262626,91a5de62-c27b-11ed-b06e-73a6e07e676e,e8359956-c27c-11ed-afb3-c3922f844a02);"
    #mysql -u dev -h db -pdev dev -e "insert into AccessLog (id, admin_kurzel, getTime, machine_id, password_id) values (3,'big-admin',2020-01-01 14:28:28.282828,a0bae91a-c27b-11ed-97d2-efbae491e385,f5b92d0e-c27c-11ed-8728-77b6c3364352);"

    # TODO: implement demo mode to populate db a bit somewhere else than vault setup script
    # while ! mysql -u dev -h db -pdev dev -e "SHOW TABLES;" | grep machine; do
    #   echo "Waiting for DB to be ready"
    #   sleep 1s
    # done

    # mysql -u dev -h db -pdev dev -e "insert into machine (id, hostname, serialnumber, enroll_time, enroll_success, disabled) values (UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),\"myHostname\",\"T35T1N600M86\",\"2020-01-01 12:12:12.121212\",True,False);"
    # mysql -u dev -h db -pdev dev -e "insert into machine (id, hostname, serialnumber, enroll_time, enroll_success, disabled) values (UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),\"myDifferentHostname\",\"T35T1N600M87\",\"2020-01-01 13:13:13.131313\",True,False);"
    # mysql -u dev -h db -pdev dev -e "insert into machine (id, hostname, serialnumber, enroll_time, enroll_success, disabled) values (UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),\"myVeryDifferentHostname\",\"T35T1N600M88\",\"2020-01-01 14:14:14.141414\",True,False);"
    # mysql -u dev -h db -pdev dev -e "insert into password (id, machine_id, password, status, password_set, password_received, password_expiry) values (UNHEX(REPLACE(\"d2de2708-c27c-11ed-8b81-4b498eb56a2e\", \"-\",\"\")),UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),\"MyEncryptedPassword1\",\"Testing\",False,\"2020-01-01 12:24:24.242424\",\"2020-01-01 12:36:36.363636\");"
    # mysql -u dev -h db -pdev dev -e "insert into password (id, machine_id, password, status, password_set, password_received, password_expiry) values (UNHEX(REPLACE(\"dbf70378-c27c-11ed-ac0a-ff5d046c5f60\", \"-\",\"\")),UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),\"MyEncryptedPassword2\",\"Testing\",False,\"2020-01-01 12:36:36.363636\",\"2020-01-01 13:00:00.000000\");"
    # mysql -u dev -h db -pdev dev -e "insert into password (id, machine_id, password, status, password_set, password_received, password_expiry) values (UNHEX(REPLACE(\"e8359956-c27c-11ed-afb3-c3922f844a02\", \"-\",\"\")),UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),\"MyEncryptedPassword3\",\"Testing\",False,\"2020-01-01 13:26:26.262626\",\"2020-01-01 13:39:39.393939\");"
    # mysql -u dev -h db -pdev dev -e "insert into password (id, machine_id, password, status, password_set, password_received, password_expiry) values (UNHEX(REPLACE(\"f04fa1fe-c27c-11ed-bdb5-8fd286cb2228\", \"-\",\"\")),UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),\"MyEncryptedPassword4\",\"Testing\",False,\"2020-01-01 13:39:39.393939\",\"2020-01-01 14:00:00.000000\");"
    # mysql -u dev -h db -pdev dev -e "insert into password (id, machine_id, password, status, password_set, password_received, password_expiry) values (UNHEX(REPLACE(\"f5b92d0e-c27c-11ed-8728-77b6c3364352\", \"-\",\"\")),UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),\"MyEncryptedPassword5\",\"Testing\",False,\"2020-01-01 14:28:28.282828\",\"2020-01-01 14:42:42.424242\");"
    # mysql -u dev -h db -pdev dev -e "insert into password (id, machine_id, password, status, password_set, password_received, password_expiry) values (UNHEX(REPLACE(\"fa5a818c-c27c-11ed-a703-d75f772b0c57\", \"-\",\"\")),UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),\"MyEncryptedPassword6\",\"Testing\",False,\"2020-01-01 14:42:42.424242\",\"2020-01-01 15:00:00.000000\");"
    # mysql -u dev -h db -pdev dev -e "insert into checkin (id, uuid, mid, checkin_time) values (1,UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),\"2020-01-01 12:13:12.121212\");"
    # mysql -u dev -h db -pdev dev -e "insert into checkin (id, uuid, mid, checkin_time) values (2,UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),\"2020-01-01 12:25:24.242424\");"
    # mysql -u dev -h db -pdev dev -e "insert into checkin (id, uuid, mid, checkin_time) values (3,UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),\"2020-01-01 13:14:13.131313\");"
    # mysql -u dev -h db -pdev dev -e "insert into checkin (id, uuid, mid, checkin_time) values (4,UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),\"2020-01-01 13:27:26.262626\");"
    # mysql -u dev -h db -pdev dev -e "insert into checkin (id, uuid, mid, checkin_time) values (5,UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),\"2020-01-01 14:15:14.141414\");"
    # mysql -u dev -h db -pdev dev -e "insert into checkin (id, uuid, mid, checkin_time) values (6,UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),\"2020-01-01 14:29:28.282828\");"
    # mysql -u dev -h db -pdev dev -e "insert into accesslog (id, admin_kurzel, getTime, machine_id, password_id) values (1,\"big-admin\",\"2020-01-01 12:24:24.242424\",UNHEX(REPLACE(\"81a70234-c27b-11ed-a0f5-fb79d6671c6e\", \"-\",\"\")),UNHEX(REPLACE(\"d2de2708-c27c-11ed-8b81-4b498eb56a2e\", \"-\",\"\")));"
    # mysql -u dev -h db -pdev dev -e "insert into accesslog (id, admin_kurzel, getTime, machine_id, password_id) values (2,\"big-admin\",\"2020-01-01 13:26:26.262626\",UNHEX(REPLACE(\"91a5de62-c27b-11ed-b06e-73a6e07e676e\", \"-\",\"\")),UNHEX(REPLACE(\"e8359956-c27c-11ed-afb3-c3922f844a02\", \"-\",\"\")));"
    # mysql -u dev -h db -pdev dev -e "insert into accesslog (id, admin_kurzel, getTime, machine_id, password_id) values (3,\"big-admin\",\"2020-01-01 14:28:28.282828\",UNHEX(REPLACE(\"a0bae91a-c27b-11ed-97d2-efbae491e385\", \"-\",\"\")),UNHEX(REPLACE(\"f5b92d0e-c27c-11ed-8728-77b6c3364352\", \"-\",\"\")));"


fi

while true; do sleep 1; done
