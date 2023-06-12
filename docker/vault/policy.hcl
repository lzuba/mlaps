path "transit/keys/client-passwords" {
  capabilities = ["read"]
}
path "transit/encrypt/client-passwords" {
  capabilities = [ "update" ]
}
path "transit/decrypt/client-passwords" {
  capabilities = [ "update" ]
}

path "pki/sign/mlaps" {
  capabilities = ["create", "update"]
}

path "auth/approle/role/client-passwords/secret-id" {
   capabilities = [ "update" ]
}