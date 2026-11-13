# Radar de Leilões

Painel local para pesquisar veículos em leilão. Os filtros começam vazios e podem ser combinados. A amostra inicial contém cinco lotes consultados em 13/11/2026. Consulte a página do lote e o edital antes de usar datas ou valores da amostra.

## Rodar no Windows

Abra o PowerShell na pasta do projeto.

```powershell
python -m pip install -r requirements.txt
python radar.py
```

Abra http://127.0.0.1:8765. Use **Atualizar coleta** para consultar os catálogos integrados. A atualização também pode ser executada com `python radar.py --collect --max-lots 8`.

O coletor inicial integra dois catálogos públicos, Mega Leilões e Pátio Vitória da Conquista. Ele examina um lote por vez em cada catálogo, com até oito lotes por fonte por padrão. O painel guarda a coleta em `coleta.json` e mantém a amostra e as consultas anteriores quando uma fonte falha. Consulte **Fontes** para ver o resultado da tentativa. A tela estática `dist/index.html` usa a amostra inicial.

O coletor lê PDFs com camada de texto. Links e modalidades não identificados ficam pendentes de confirmação. A cobertura das 27 Juntas, o DJEN, OCR, agendamento e publicação são etapas posteriores.

## Testes

```powershell
python -m unittest discover -s tests -v
node --check dist/app.js
```

## Hospedar na Vercel e coletar com GitHub Actions

1. No Supabase, use um usuário de e-mail e senha para acessar o painel. Se a base ainda não tiver as tabelas do Radar, execute `supabase.sql` no SQL Editor.
2. Configure a política de leitura descrita abaixo. Importe o repositório na Vercel como projeto Flask e configure `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `RADAR_OWNER_EMAIL` e `RADAR_SESSION_SECRET` (segredo aleatório de pelo menos 32 caracteres). O plano Hobby é para uso pessoal e não comercial.
3. Em **Settings → Secrets and variables → Actions** do GitHub, configure os secrets `SUPABASE_URL` e `SUPABASE_SECRET_KEY`. Use os campos de segredos de cada serviço e mantenha as chaves fora dos arquivos versionados.
4. Abra **Actions → Coleta do Radar → Run workflow** e confira o resultado. As próximas coletas são programadas para 08h17 e 18h17, no horário de João Pessoa. O GitHub pode desativar agendamentos após 60 dias sem atividade em repositório público.
5. Depois de verificar o painel, adicione `radar.escalarapida.com.br` na Vercel e aponte o CNAME `radar` para o destino indicado no projeto.

O painel lê o catálogo com o token do usuário autenticado. Para instalar em outra base, execute no SQL Editor, substituindo o e-mail de exemplo pelo mesmo e-mail configurado em `RADAR_OWNER_EMAIL`.

```sql
grant select on public.radar_snapshot to authenticated;
create policy radar_owner_catalog_read on public.radar_snapshot
for select to authenticated
using (id = 'main' and (select auth.uid()) is not null
       and lower((select auth.jwt()) ->> 'email') = 'owner@example.com');
```

## Hospedar no Render com Supabase

1. Abra o SQL Editor do projeto Supabase escolhido e execute `supabase.sql`. O script cria tabelas específicas do radar para o catálogo e as mudanças de preço.
2. Em Authentication, use ou crie um usuário de e-mail e senha para o painel. No Render, informe esse e-mail em `RADAR_OWNER_EMAIL`.
3. No Render, selecione este repositório como fonte e configure o Blueprint `render.yaml`. Informe a URL HTTPS do projeto e as chaves de servidor e publicável nos campos de ambiente indicados.
4. Execute manualmente o cron `radar-coleta` e confirme as fontes, lotes e fotos no painel autenticado. O cron fica configurado para 08h e 18h de João Pessoa (11h e 21h UTC).
5. Adicione `radar.escalarapida.com.br` como domínio do serviço web no Render e crie o CNAME `radar` na zona DNS que administra o domínio, usando o destino exibido pelo Render.

O painel mostra imagens vinculadas aos anúncios por URL. Em Fontes, o filtro cobre as 27 UFs, com link para cada Junta e registros documentados quando disponíveis.

