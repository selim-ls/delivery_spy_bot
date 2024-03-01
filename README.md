# Delivery Spy Bot

Le Delivery Spy Bot est un bot Telegram conçu pour surveiller les offres publiées par les restaurants sur les plateformes de livraison comme Deliveroo et UberEats. Le bot permet aux utilisateurs de s'abonner à des alertes pour être informés lorsque de nouvelles offres sont disponibles.

## Fonctionnalités

- Enregistrement des liens vers les pages des restaurants sur Deliveroo et UberEats.
- Surveillance des pages pour détecter les nouvelles offres publiées.
- Notification des utilisateurs abonnés via Telegram lorsque de nouvelles offres sont détectées.
- Possibilité d'arrêter les alertes pour des restaurants spécifiques ou pour tous les restaurants.

## Configuration

Pour exécuter le bot, assurez-vous d'avoir Python installé sur votre système. Installez ensuite les dépendances en exécutant `pip install -r requirements.txt`. 

Créez un fichier `.env` contenant les informations sensibles telles que le token du bot Telegram.

```
BOT_TOKEN=your_bot_token_here
```

Enfin, lancez le bot en exécutant le script principal `main.py`.

## Auteur

Ce projet a été développé par Selim Le Strat.