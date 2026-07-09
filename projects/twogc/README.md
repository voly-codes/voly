# 2GC / MTS B2B Store — VOLY combat missions

Combat-задания для Cursor через VOLY (формат как `projects/smarty/missions/`).

## Запуск

```bash
cd /home/lanies/git/codeops/voly
source .venv/bin/activate   # если есть

# Список миссий
PYTHONPATH=. python -m projects.twogc twogc combat list

# Просмотр шагов
PYTHONPATH=. python -m projects.twogc twogc combat show mts-cloudbridge-relay-bundle

# Запуск (5 шагов, sequential)
PYTHONPATH=. python -m projects.twogc twogc combat run mts-cloudbridge-relay-bundle --sequential
```

## Переменные окружения

| Переменная | По умолчанию |
|------------|--------------|
| `TGC_ROOT` | `/home/lanies/git/2GC` |
| `MTS_2GC_PATH` | `$TGC_ROOT/mts-2gc` |
| `RELAY_INSTALLER_PATH` | `$TGC_ROOT/cloudbridge-relay-installer` |

## Миссии

| Имя | Описание |
|-----|----------|
| `mts-cloudbridge-relay-bundle` | OVA + Terraform + pack + API smoke + runbook |

## Альтернатива без plugin

Один шаг через `voly runner`:

```bash
cd /home/lanies/git/codeops/voly
voly runner cursor "STEP 1/5 из missions/mts-cloudbridge-relay-bundle.yaml" \
  --cwd /home/lanies/git/2GC/mts-2gc
```
