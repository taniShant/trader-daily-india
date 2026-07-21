# Cross-Account Bedrock Sidecar

This sidecar prepares IAM trust for this shape:

```text
ECS runtime account: 873660758628
Bedrock provider account: 632943041262
Region: eu-west-2
```

It does not change the normal single-account deployment path. The default CDK app remains `app.py`; it still deploys only `svc-trd-PlatformStack` and `svc-trd-AgentRuntimeStack`.

## Files

```text
cicd/apps/cross_account_bedrock_app.py
cicd/stacks/cross_account_bedrock_stack.py
cicd/env/cross-account-bedrock.json
tests/unit/test_cross_account_bedrock_stack.py
docs/cross_account_bedrock_sidecar.md
```

Deleting these files removes the sidecar and leaves the original `873660758628` deployment path intact.

## What It Creates

Provider account `632943041262`:

- Stack: `svc-trd-BedrockProviderRoleStack`
- Role: `trd-bedrock-invoke-from-873-role`
- Trusts: `arn:aws:iam::873660758628:role/trd-prod-ecs-taskexecute-role`
- Requires external ID: `trd-bedrock-prod-632-from-873`
- Allows Bedrock invoke/converse actions for the configured model IDs.

Consumer account `873660758628`:

- Stack: `svc-trd-BedrockConsumerPermissionStack`
- Imports existing role: `trd-prod-ecs-taskexecute-role`
- Adds permission to assume the provider role in `632943041262`.

## Deploy Order

Deploy the provider role first:

```bash
cdk -a ".venv/bin/python cicd/apps/cross_account_bedrock_app.py" deploy svc-trd-BedrockProviderRoleStack --profile naresh --require-approval never
```

Then deploy the consumer permission:

```bash
cdk -a ".venv/bin/python cicd/apps/cross_account_bedrock_app.py" deploy svc-trd-BedrockConsumerPermissionStack --profile default --require-approval never
```

## Smoke Test

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::632943041262:role/trd-bedrock-invoke-from-873-role \
  --role-session-name trd-bedrock-smoke \
  --external-id trd-bedrock-prod-632-from-873 \
  --profile default
```

This only proves the IAM handshake. The runtime still needs a later, small Bedrock client change before the bot uses the assumed role credentials.

## Runtime Switch

The runtime adapter is present but disabled by default in `cicd/env/prod.json`:

```json
"cross_account_bedrock": {
  "enabled": false,
  "role_arn": "arn:aws:iam::632943041262:role/trd-bedrock-invoke-from-873-role",
  "external_id": "trd-bedrock-prod-632-from-873",
  "region": "eu-west-2",
  "session_name": "trd-bedrock-runtime"
}
```

When disabled, `agent/main.py` creates the Strands `BedrockModel` exactly as before, using the ECS task role in `873660758628`.

To switch on the cross-account path later, set:

```json
"enabled": true
```

Then redeploy the ECS task definition. The bot will assume the provider role in `632943041262` before constructing the Bedrock boto session.
