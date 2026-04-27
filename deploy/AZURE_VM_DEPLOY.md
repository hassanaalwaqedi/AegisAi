# Azure VM Deployment

This deployment path is for a single Azure Linux VM running Docker, with Azure Database for PostgreSQL used as the backing database.

## 1. Copy the project to the VM

Recommended if you have a remote Git repository:

```bash
git clone <your-repo-url> ~/AegisAi
cd ~/AegisAi
```

Quick archive-based option from your local Windows machine:

```powershell
tar.exe --exclude=.git --exclude=venv312 --exclude=.env --exclude=data/output --exclude=models -czf C:\Users\hsana\aegisai-deploy.tgz -C C:\Users\hsana AegisAi
scp -i C:\Users\hsana\Downloads\Aegisai_key.pem C:\Users\hsana\aegisai-deploy.tgz azureuser@YOUR_VM_PUBLIC_IP:~/
```

Then on the VM:

```bash
mkdir -p ~/AegisAi
tar -xzf ~/aegisai-deploy.tgz -C ~/
cd ~/AegisAi
```

## 2. Install Docker on the VM

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

## 3. Create the deployment env file

```bash
cp deploy/azure-vm.env.example deploy/azure-vm.env
nano deploy/azure-vm.env
```

Update at least:

- `DATABASE_URL`
- `AEGIS_API_KEY`
- `AEGIS_ALLOWED_ORIGINS`

For Azure Database for PostgreSQL Flexible Server, use the fully qualified server name and `sslmode=require`.

## 4. Start the app

```bash
mkdir -p data/input data/output models
docker compose -f deploy/azure-vm-compose.yml --env-file deploy/azure-vm.env up -d --build
```

## 5. Check logs and health

```bash
docker compose -f deploy/azure-vm-compose.yml ps
docker compose -f deploy/azure-vm-compose.yml logs -f api
curl http://localhost:8080/status/health
```

## 6. Open the app

- API root: `http://YOUR_VM_PUBLIC_IP:8080/`
- Dashboard: `http://YOUR_VM_PUBLIC_IP:8080/dashboard`

## Notes

- The VM must allow inbound TCP `8080` if you want to access the API directly from the internet.
- If you later add a domain and reverse proxy, you can keep the container on port `8080` and terminate HTTPS in front of it.
- This compose file uses your managed PostgreSQL service instead of local SQLite.
