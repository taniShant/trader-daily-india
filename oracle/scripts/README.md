# Oracle Deployment Scripts

These scripts target the existing Oracle VM with static IP `80.225.242.6`.

P1-WP05 uses scripts rather than Terraform because the VM/static IP already exists.

Dry run:

```bash
oracle/scripts/deploy_execution_proxy.sh --dry-run
```

Real deploy requires:

```bash
export ORACLE_HOST=80.225.242.6
export ORACLE_USER=opc
export ORACLE_SSH_KEY=/path/to/oracle_private_key
export ORACLE_PROXY_SHARED_SECRET=change-me
oracle/scripts/deploy_execution_proxy.sh
```

The script copies `oracle/execution-proxy/` to the VM, builds the Docker image on the VM, writes a remote `.env`, starts the container on port `8080`, and checks `/health`.
