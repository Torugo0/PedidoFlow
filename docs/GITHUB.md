# Publicacao no GitHub

O projeto ja possui repositorio Git local, commit inicial e `.gitignore` para
banco, ambiente, cache e pesos grandes. A publicacao depende da conta e do
repositorio escolhidos pelo grupo.

Depois de criar um repositorio vazio no GitHub, execute no terminal integrado:

```powershell
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
git push -u origin main
```

Antes do push, confira `git status` e confirme que `outputs/`, `.venv/`, o banco
SQLite e arquivos `.safetensors` nao aparecem. Os datasets sinteticos, configs,
codigo, testes e relatorios leves devem aparecer.

Nao adicione tokens, chaves ou credenciais ao repositorio.
