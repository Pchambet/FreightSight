# Sauvegardes — questions ouvertes

## 1. AES-GCM plutôt que `age`

Demandé : « age si dispo en pip, sinon AES-GCM ». `age` n'a pas d'implémentation Python de référence
maintenue par ses auteurs (les paquets PyPI sont des portages tiers), et l'alternative est d'embarquer
le binaire Go dans l'image. Pour une primitive, ça fait beaucoup de surface. C'est donc AES-256-GCM
via `cryptography`, qu'on porte déjà pour la vérification des JWT Clerk.

Le format est volontairement ennuyeux et auto-descriptif : `FSBK1` + nonce 12 octets + ciphertext GCM,
l'en-tête servant de données authentifiées. Un fichier qui n'a pas cette signature est refusé avec un
message clair plutôt que de produire de la bouillie.

→ Si tu préfères `age` (interopérabilité, clés SSH, `age -d` en ligne de commande sans notre code),
c'est un adapter à écrire ; le reste ne bouge pas.

## 2. La clé de chiffrement est un point de défaillance

Si `BACKUP_ENCRYPTION_KEY` ne vit que dans Railway, perdre le compte Railway revient à perdre les
sauvegardes **et** la clé. C'est écrit dans la doc ops, mais c'est une action humaine : **Pierre doit
mettre la clé dans un gestionnaire de mots de passe, hors du fournisseur.** Tant que ce n'est pas
fait, la sauvegarde hors fournisseur ne protège pas du scénario qu'elle vise.

## 3. Le test de restauration ne tourne probablement pas en CI

`test_a_dump_restores_with_every_row` fait un vrai aller-retour (dump → chiffrement → déchiffrement →
restauration dans une base neuve → comparaison du nombre de lignes par table), mais il se saute tout
seul si `pg_dump` est absent **ou d'une majeure différente du serveur** — `pg_dump` refuse un serveur
plus récent que lui. Le runner GitHub n'a pas forcément un client 17.

→ **Une ligne à ajouter au job `backend` de la CI** (fichier de freightsight-fa) pour qu'il tourne
vraiment :

```yaml
- run: sudo apt-get update && sudo apt-get install -y postgresql-client-17
```

En attendant, l'aller-retour a été vérifié à la main sur le Postgres 17 local : dump de 125 Ko,
chiffré, restauré dans une base neuve, 28 tables et les lignes attendues.

## 4. Ce que la rétention fait exactement

30 jours glissants **comptés depuis la sauvegarde la plus récente**, pas les 30 dernières
sauvegardes : une semaine où le cron était cassé ne doit pas faire passer un dump de l'an dernier pour
récent. Plus la première sauvegarde de chacun des 12 derniers mois. Les dates viennent de la clé de
l'objet, pas de sa date de modification, pour qu'un fichier réenvoyé ne rajeunisse pas.

Rien ne supprime les objets qui ne correspondent pas au motif de nom : le préfixe peut contenir autre
chose sans risque.

## 5. Pas de vérification automatique des sauvegardes

Le job écrit une ligne de log JSON (taille, durée, sha256) et sort en code non nul s'il échoue, ce que
le cron Railway remonte. Ce qu'il ne fait **pas** : restaurer périodiquement pour vérifier. C'est le
vrai test d'une sauvegarde, et ça demande une base jetable et du temps machine.

→ Proposition : un job mensuel qui restaure la dernière sauvegarde dans une base temporaire, compte
les lignes, la supprime et lève une alerte si le compte s'effondre. À faire quand il y aura de vraies
données à perdre.

## 6. Divers

- La restauration refuse de tourner sans terminal si `--yes` n'est pas donné : c'est une commande qui
  écrit dans une base, elle ne doit pas être lançable par accident depuis un script.
- Rien ne sauvegarde les fichiers de factures s'ils passent un jour sur S3 : ils seront dans le bucket
  Scaleway, pas dans le dump. Aujourd'hui ils sont en base, donc dans le dump.
