# Secrets Management

This guide covers secure secrets management patterns for Knowledge Mapper in production environments.

## Overview

### What Qualifies as a Secret

Secrets include any sensitive data that must be protected:

| Category | Examples |
|----------|----------|
| Database Credentials | `DATABASE_URL`, `MIGRATION_DATABASE_URL` |
| Cache Credentials | `REDIS_URL` |
| OAuth/Auth | `OAUTH_CLIENT_SECRET` |
| API Keys | Third-party service keys |
| TLS Certificates | Private keys for HTTPS |

### Golden Rules

1. **Never commit secrets to version control** - Even in private repositories
2. **Never log secrets** - Ensure secrets are redacted in logs and error messages
3. **Rotate secrets regularly** - Automate rotation where possible
4. **Use least-privilege access** - Applications should only access secrets they need
5. **Audit secret access** - Track who and what accessed secrets

---

## Kubernetes Secrets (Development/Simple Production)

Kubernetes Secrets provide a basic mechanism for storing sensitive data.

### Creating Secrets via CLI

```bash
# Create from literal values
kubectl create secret generic knowledge-mapper-secrets \
  --namespace knowledge-mapper \
  --from-literal=DATABASE_URL='postgresql+asyncpg://appuser:password@db-host:5432/knowledge_mapper_db' \
  --from-literal=MIGRATION_DATABASE_URL='postgresql+asyncpg://migrator:password@db-host:5432/knowledge_mapper_db' \
  --from-literal=REDIS_URL='redis://default:password@redis-host:6379/0'
```

### Creating Secrets from File

```bash
# Create from environment file (more secure - no secrets in shell history)
kubectl create secret generic knowledge-mapper-secrets \
  --namespace knowledge-mapper \
  --from-env-file=secrets.env
```

Example `secrets.env` file (do NOT commit this):
```bash
DATABASE_URL=postgresql+asyncpg://appuser:actualpassword@db-host:5432/knowledge_mapper_db
MIGRATION_DATABASE_URL=postgresql+asyncpg://migrator:actualpassword@db-host:5432/knowledge_mapper_db
REDIS_URL=redis://default:actualpassword@redis-host:6379/0
```

### Viewing Secrets

```bash
# List secrets in namespace
kubectl get secrets -n knowledge-mapper

# View secret metadata (not values)
kubectl describe secret knowledge-mapper-secrets -n knowledge-mapper

# View secret data (base64 encoded)
kubectl get secret knowledge-mapper-secrets -n knowledge-mapper -o yaml

# Decode a specific value
kubectl get secret knowledge-mapper-secrets -n knowledge-mapper \
  -o jsonpath='{.data.DATABASE_URL}' | base64 -d
```

### Updating Secrets

```bash
# Delete and recreate (simplest approach)
kubectl delete secret knowledge-mapper-secrets -n knowledge-mapper
kubectl create secret generic knowledge-mapper-secrets \
  --namespace knowledge-mapper \
  --from-env-file=secrets.env

# Or use patch for individual values
kubectl patch secret knowledge-mapper-secrets -n knowledge-mapper \
  --type='json' \
  -p='[{"op": "replace", "path": "/data/DATABASE_URL", "value": "'$(echo -n 'new-url' | base64)'"}]'
```

### Limitations

- Secrets are base64 encoded, not encrypted at rest (unless you enable encryption at rest)
- Anyone with access to the namespace can read secrets
- No audit trail of secret access
- No automatic rotation

---

## HashiCorp Vault Integration

For production environments, HashiCorp Vault provides enterprise-grade secrets management with dynamic secrets, automatic rotation, and comprehensive audit logging.

### Architecture Overview

```
+----------------+     +-------+     +------------+
| Application    |---->| Vault |---->| Backend    |
| (Pod)          |     | Agent |     | Secrets    |
+----------------+     +-------+     +------------+
       ^                   |
       |                   v
       +------- Secrets injected as files or env vars
```

### Installing Vault Agent Injector

```bash
# Add HashiCorp Helm repo
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

# Install Vault injector (assumes Vault server is running elsewhere)
helm install vault hashicorp/vault \
  --namespace vault \
  --create-namespace \
  --set injector.enabled=true \
  --set server.enabled=false \
  --set global.externalVaultAddr="https://vault.example.com"
```

### Configuring Kubernetes Authentication

```bash
# Enable Kubernetes auth in Vault
vault auth enable kubernetes

# Configure Kubernetes auth
vault write auth/kubernetes/config \
  kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443" \
  token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  kubernetes_ca_cert="$(cat /var/run/secrets/kubernetes.io/serviceaccount/ca.crt)"

# Create policy for the application
vault policy write knowledge-mapper - <<EOF
path "secret/data/knowledge-mapper/*" {
  capabilities = ["read"]
}
EOF

# Create role for service account
vault write auth/kubernetes/role/knowledge-mapper \
  bound_service_account_names=knowledge-mapper-backend \
  bound_service_account_namespaces=knowledge-mapper \
  policies=knowledge-mapper \
  ttl=24h
```

### Storing Secrets in Vault

```bash
# Store database secrets
vault kv put secret/knowledge-mapper/database \
  url="postgresql+asyncpg://appuser:password@db-host:5432/knowledge_mapper_db" \
  migration_url="postgresql+asyncpg://migrator:password@db-host:5432/knowledge_mapper_db"

# Store Redis secrets
vault kv put secret/knowledge-mapper/redis \
  url="redis://default:password@redis-host:6379/0"
```

### Deployment with Vault Agent Sidecar

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: knowledge-mapper
spec:
  template:
    metadata:
      annotations:
        # Enable Vault Agent injection
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "knowledge-mapper"

        # Inject database secrets
        vault.hashicorp.com/agent-inject-secret-database: "secret/data/knowledge-mapper/database"
        vault.hashicorp.com/agent-inject-template-database: |
          {{- with secret "secret/data/knowledge-mapper/database" -}}
          export DATABASE_URL="{{ .Data.data.url }}"
          export MIGRATION_DATABASE_URL="{{ .Data.data.migration_url }}"
          {{- end }}

        # Inject Redis secrets
        vault.hashicorp.com/agent-inject-secret-redis: "secret/data/knowledge-mapper/redis"
        vault.hashicorp.com/agent-inject-template-redis: |
          {{- with secret "secret/data/knowledge-mapper/redis" -}}
          export REDIS_URL="{{ .Data.data.url }}"
          {{- end }}
    spec:
      serviceAccountName: knowledge-mapper-backend
      containers:
        - name: backend
          command:
            - /bin/sh
            - -c
            - |
              source /vault/secrets/database
              source /vault/secrets/redis
              exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Dynamic Database Credentials (Advanced)

Vault can generate database credentials on-demand with automatic expiration:

```bash
# Enable database secrets engine
vault secrets enable database

# Configure PostgreSQL connection
vault write database/config/knowledge_mapper_db \
  plugin_name=postgresql-database-plugin \
  allowed_roles="knowledge-mapper-app" \
  connection_url="postgresql://{{username}}:{{password}}@db-host:5432/knowledge_mapper_db" \
  username="vault_admin" \
  password="vault_admin_password"

# Create role for dynamic credentials
vault write database/roles/knowledge-mapper-app \
  db_name=knowledge_mapper_db \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"
```

---

## AWS Secrets Manager Integration

For AWS deployments, AWS Secrets Manager provides managed secrets storage with integration via the External Secrets Operator.

### Installing External Secrets Operator

```bash
# Add External Secrets Helm repo
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

# Install External Secrets Operator
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace
```

### Setting Up IAM Role for Service Account (IRSA)

```bash
# Create IAM policy
cat > /tmp/secrets-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:knowledge-mapper/*"
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name knowledge-mapper-secrets-policy \
  --policy-document file:///tmp/secrets-policy.json

# Create IAM role for service account
eksctl create iamserviceaccount \
  --name external-secrets-sa \
  --namespace knowledge-mapper \
  --cluster your-cluster-name \
  --attach-policy-arn arn:aws:iam::ACCOUNT_ID:policy/knowledge-mapper-secrets-policy \
  --approve
```

### Storing Secrets in AWS Secrets Manager

```bash
# Store database secrets
aws secretsmanager create-secret \
  --name knowledge-mapper/database \
  --secret-string '{"url":"postgresql+asyncpg://appuser:password@db-host:5432/knowledge_mapper_db","migration_url":"postgresql+asyncpg://migrator:password@db-host:5432/knowledge_mapper_db"}'

# Store Redis secrets
aws secretsmanager create-secret \
  --name knowledge-mapper/redis \
  --secret-string '{"url":"redis://default:password@redis-host:6379/0"}'
```

### SecretStore Configuration

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-manager
  namespace: knowledge-mapper
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
```

### ExternalSecret Configuration

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: knowledge-mapper-secrets
  namespace: knowledge-mapper
spec:
  refreshInterval: 1h  # How often to sync secrets
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: knowledge-mapper-secrets  # K8s Secret name
    creationPolicy: Owner
  data:
    # Database secrets
    - secretKey: DATABASE_URL
      remoteRef:
        key: knowledge-mapper/database
        property: url
    - secretKey: MIGRATION_DATABASE_URL
      remoteRef:
        key: knowledge-mapper/database
        property: migration_url
    # Redis secrets
    - secretKey: REDIS_URL
      remoteRef:
        key: knowledge-mapper/redis
        property: url
```

---

## Sealed Secrets (GitOps)

For GitOps workflows, Bitnami Sealed Secrets allows encrypting secrets that can be safely committed to Git.

### Architecture Overview

```
+----------+     +-------------------+     +-----------------+
| Developer|---->| kubeseal encrypt  |---->| Git Repository  |
+----------+     +-------------------+     +-----------------+
                                                    |
                                                    v
                                           +-----------------+
                                           | ArgoCD/Flux     |
                                           +-----------------+
                                                    |
                                                    v
                        +------------------+  +-------------------+
                        | K8s Secret       |<-| Sealed Secrets    |
                        | (decrypted)      |  | Controller        |
                        +------------------+  +-------------------+
```

### Installing Sealed Secrets

```bash
# Install kubeseal CLI (macOS)
brew install kubeseal

# Install kubeseal CLI (Linux)
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/kubeseal-0.24.0-linux-amd64.tar.gz
tar -xvzf kubeseal-0.24.0-linux-amd64.tar.gz
sudo install -m 755 kubeseal /usr/local/bin/kubeseal

# Install Sealed Secrets controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml
```

### Creating Sealed Secrets

```bash
# Create a regular secret (dry-run, not applied)
kubectl create secret generic knowledge-mapper-secrets \
  --namespace knowledge-mapper \
  --from-literal=DATABASE_URL='postgresql+asyncpg://appuser:password@db-host:5432/knowledge_mapper_db' \
  --from-literal=MIGRATION_DATABASE_URL='postgresql+asyncpg://migrator:password@db-host:5432/knowledge_mapper_db' \
  --from-literal=REDIS_URL='redis://default:password@redis-host:6379/0' \
  --dry-run=client \
  -o yaml > /tmp/secret.yaml

# Seal the secret
kubeseal --format=yaml < /tmp/secret.yaml > k8s/base/sealed-secrets.yaml

# Clean up unencrypted file
rm /tmp/secret.yaml

# The sealed-secrets.yaml can be safely committed to git
```

### Sealed Secret Manifest

```yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: knowledge-mapper-secrets
  namespace: knowledge-mapper
spec:
  encryptedData:
    DATABASE_URL: AgBY7w3j...encrypted...
    MIGRATION_DATABASE_URL: AgBY7w3j...encrypted...
    REDIS_URL: AgBY7w3j...encrypted...
  template:
    metadata:
      name: knowledge-mapper-secrets
      namespace: knowledge-mapper
    type: Opaque
```

### Applying Sealed Secrets

```bash
# Apply the sealed secret
kubectl apply -f k8s/base/sealed-secrets.yaml

# The controller will decrypt it and create a regular Secret
kubectl get secret knowledge-mapper-secrets -n knowledge-mapper
```

### Updating Sealed Secrets

```bash
# Create new secret with updated values
kubectl create secret generic knowledge-mapper-secrets \
  --namespace knowledge-mapper \
  --from-literal=DATABASE_URL='new-url' \
  --from-literal=MIGRATION_DATABASE_URL='new-migration-url' \
  --from-literal=REDIS_URL='new-redis-url' \
  --dry-run=client \
  -o yaml | kubeseal --format=yaml > k8s/base/sealed-secrets.yaml

# Commit and push
git add k8s/base/sealed-secrets.yaml
git commit -m "Update sealed secrets"
git push
```

---

## Secret Rotation

### Manual Rotation Process

1. **Generate new credentials** in the secrets manager
2. **Update the application** with new credentials (via Secret update or redeploy)
3. **Restart pods** to pick up new secrets
4. **Verify** application is functioning with new credentials
5. **Revoke old credentials** after verification

```bash
# Rolling restart to pick up new secrets
kubectl rollout restart deployment/backend -n knowledge-mapper

# Watch rollout status
kubectl rollout status deployment/backend -n knowledge-mapper
```

### Automated Rotation

Consider these approaches for automated rotation:

| Approach | Best For | Notes |
|----------|----------|-------|
| Vault Dynamic Secrets | Database credentials | Auto-rotating with TTL |
| AWS RDS IAM Auth | AWS RDS databases | No password needed |
| External Secrets Refresh | AWS/GCP Secrets | Sync on interval |
| cert-manager | TLS certificates | Auto-renewal |

---

## Best Practices Summary

### Do

- Use a secrets manager in production (Vault, AWS SM, GCP Secret Manager)
- Rotate secrets regularly (automate where possible)
- Use separate secrets per environment (dev/staging/prod)
- Audit secret access
- Use least-privilege access
- Encrypt secrets at rest in Kubernetes (`EncryptionConfiguration`)
- Use RBAC to restrict secret access

### Do Not

- Commit secrets to git (even in private repos)
- Log secrets or include in error messages
- Share secrets across environments
- Use default/example passwords in production
- Store secrets in ConfigMaps
- Pass secrets via command-line arguments (visible in process list)
- Store secrets in container images

---

## Troubleshooting

### Secret Not Found

```bash
# Check secret exists
kubectl get secret knowledge-mapper-secrets -n knowledge-mapper

# Check secret is referenced in deployment
kubectl get deployment backend -n knowledge-mapper -o yaml | grep -A 10 envFrom

# Check secret is mounted in pod
kubectl exec -n knowledge-mapper deploy/backend -- env | grep DATABASE
```

### Permission Denied (External Secrets)

```bash
# Check External Secrets Operator logs
kubectl logs -n external-secrets deployment/external-secrets

# Check SecretStore status
kubectl describe secretstore aws-secrets-manager -n knowledge-mapper

# Check ExternalSecret status
kubectl describe externalsecret knowledge-mapper-secrets -n knowledge-mapper
```

### Permission Denied (Vault)

```bash
# Check Vault Agent logs
kubectl logs -n knowledge-mapper deploy/backend -c vault-agent

# Verify service account
kubectl get sa knowledge-mapper-backend -n knowledge-mapper

# Test Vault authentication manually
vault login -method=kubernetes role=knowledge-mapper
vault kv get secret/knowledge-mapper/database
```

### Sealed Secrets Not Decrypting

```bash
# Check Sealed Secrets controller logs
kubectl logs -n kube-system deployment/sealed-secrets-controller

# Verify sealed secret
kubectl get sealedsecret knowledge-mapper-secrets -n knowledge-mapper

# Check if namespace/name matches
# Sealed secrets are scoped to namespace and name by default
```

---

## Related Documentation

- [Environment Configuration](./environment-configuration.md) - Full variable reference
- [Configuration Validation](./configuration-validation.md) - Troubleshooting guide
- [../DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment procedures
