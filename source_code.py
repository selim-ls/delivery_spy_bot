import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime, timedelta
import time
import schedule
import random
import string
import unicodedata
import numpy as np
import asyncio
import logging
import os
from dotenv import load_dotenv
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, Updater, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler, JobQueue, ConversationHandler


def generer_agents_utilisateurs(n=10):
    '''Cette fonction génère automatiquement n agents utilisateurs pour les requêtes html'''
    agents_utilisateurs = []

    for _ in range(n):
        agent = f"Mozilla/5.0 ({random.choice(['Windows NT 10.0', 'Windows NT 6.1', 'Macintosh', 'X11'])}; "
        agent += f"{random.choice(['Win64; x64', 'Win64; x32', 'Macintosh Intel', 'Linux x86_64'])}) "
        agent += f"AppleWebKit/{''.join(random.choices(string.ascii_letters + string.digits, k=3))} "
        agent += f"(KHTML, like Gecko) Chrome/{random.randint(50, 80)}.0.{random.randint(1000, 9999)}. "
        agent += f"Safari/{''.join(random.choices(string.digits, k=3))}"
        agents_utilisateurs.append(agent)

    return agents_utilisateurs

agents = generer_agents_utilisateurs(10)

headers = {
        'User-Agent': random.choice(agents),
        'Referer': 'https://www.google.com/'
    }

def filter_out_unicode(t):
    '''Filtre les caractères unicode et renvoie un texte lisible'''
    cleaned_text = unicodedata.normalize("NFKD", t.text)
    cleaned_text = re.sub(r'[\u202a\u202c\u200b]', '', cleaned_text)
    return cleaned_text

def clean_url(url):
    '''Renvoie une structure d'url uniforme en supprimant la query et ce qui suit'''
    return url.split('?')[0]

def recuperer_nom(url, headers):
    '''Récupère le nom du restaurant à partir d'un url Deliveroo ou UberEats'''
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        if url.startswith('https://deliveroo.fr/'):
            nom = soup.find('h1', class_='ccl-cc80f737565f5a11 ccl-de2d30f2fc9eac3e ccl-05906e3f85528c85 ccl-483b12e41c465cc7').text
        elif url.startswith('https://www.ubereats.com/'):
            nom = soup.find('h1', {'data-testid': 'store-title-summary'}).text
        return nom
    else:
        print("La requête a échoué :", response.status_code)
        return None
    
def recuperer_offre(url, headers):
    '''Récupère l'offre proposée par le restaurant à partir d'un url Deliveroo ou UberEats (uniquement en France, non optimisée pour ODC)'''
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        if url.startswith('https://deliveroo.fr/'):
            # Menu Discount
            titre = soup.find(string=re.compile("sur tout le menu"))
            mov = soup.find(string=re.compile("Pour les commandes"))
            condition = soup.find(string=re.compile("Offre valable"))
            if titre and mov and condition:
                return "{}: {}: {}".format(filter_out_unicode(titre), filter_out_unicode(mov), filter_out_unicode(condition))
            elif titre and mov:
                return "{}: {}".format(filter_out_unicode(titre), filter_out_unicode(mov))
            elif titre and condition:
                return "{}: {}".format(filter_out_unicode(titre), filter_out_unicode(condition))
            elif titre:
                return "{}".format(filter_out_unicode(titre))
            # BOGO, Free Item, Special Offer
            else:
                promo = ['1 acheté = 1 offert', 'Produits offerts', 'Produit offert', 'Offres', 'Sélection de produits à -20 %', 
                        'Sélection de produits à -25 %','Sélection de produits à -30 %', 'Sélection de produits à -50 %']
                title = filter_out_unicode(soup.find('h2', class_='ccl-cc80f737565f5a11 ccl-de2d30f2fc9eac3e ccl-b2e0b0752cacdc85 ccl-6bb677476f666349'))
                if title in promo:
                    mov = soup.find(string=re.compile("Commandez pour"))
                    carousel = soup.find_all('div', class_='MenuItemCard-03b1bfbfe7cb723c MenuItemCard-b3fbc115b81b9e1e')
                    produits = []
                    for produit in carousel:
                        nom_produit = produit.find('p', class_='ccl-649204f2a8e630fd ccl-a396bc55704a9c8a ccl-0956b2f88e605eb8 ccl-ff5caa8a6f2b96d0 ccl-40ad99f7b47f3781')
                        produits.append(filter_out_unicode(nom_produit))
                    return '{}: {} sur {}'.format(title, filter_out_unicode(mov), sorted(produits)) if mov else '{} sur {}'.format(title, sorted(produits))
                else:
                    return np.nan
        elif url.startswith('https://www.ubereats.com/'):
            # Problème temps de chargement des pages UE
            promo = ['1 acheté(s) = 1 offert(s)', 'Offres', 'Prix réduit(s)', "Offert dès 15 € d'achat (ajouter au panier)", 
                    "Offert dès 20 € d'achat (ajouter au panier)", ]
            title = soup.find('span', class_='')
            clean_title = filter_out_unicode(title).strip()
            if clean_title in promo:
                carousel = title.find_parent('div').find_parent('div')
                produits = [filter_out_unicode(produit) for produit in carousel.find_all('div', class_='be cu bg dv b1')]
                return '{} sur {}'.format(clean_title, sorted(produits))
            else:
                return np.nan
    else:
        print("La requête a échoué :", response.status_code)
        return None
    
def save_and_update_offre(dict_url, df_offres):
    '''Met à jour le DataFrame existant avec les nouvelles entrées de dict_url, ainsi que les offres actuelles'''
    df_offres.drop(columns='offre_t-1', inplace=True)
    df_offres['offre_actuelle'] = df_offres['offre_actuelle'].astype(object)
    df_offres.rename(columns={'offre_actuelle': 'offre_t-1'}, inplace=True)
    for index, row in df_offres.iterrows():
                nouvelle_offre = recuperer_offre(row['url_restaurant'], headers)
                df_offres.at[index, 'offre_actuelle'] = nouvelle_offre
    for user, url in dict_url.items():
        if url not in df_offres['url_restaurant'].values:
            url_restaurant = clean_url(url)
            nom_restaurant = recuperer_nom(url_restaurant, headers)
            nouvelle_offre = recuperer_offre(url_restaurant, headers)
            user_id = user
            new_line = pd.DataFrame([[user_id, url_restaurant, nom_restaurant, np.nan, nouvelle_offre]],
                                    columns=['user_id', 'url_restaurant', 'nom_restaurant', 'offre_t-1', 'offre_actuelle'])
            df_offres = pd.concat([df_offres, new_line], ignore_index=True)
    df_offres.drop_duplicates(subset=['url_restaurant'], inplace=True)
    file_name = 'df_offres.csv'
    df_offres.to_csv(file_name, index=False)
    return df_offres
            
def detect_offre(df_offres):
    '''Compare les colonnes offre_t-1 et offre_actuelle de df_offres afin de détecter les offres récemment mises en ligne'''
    k = []
    for i in range(0, len(df_offres)):
        if pd.isna(df_offres['offre_actuelle'].iloc[i]) is False:
            if df_offres['offre_t-1'].iloc[i] != df_offres['offre_actuelle'].iloc[i]:
                user_id = int(df_offres['user_id'].iloc[i])
                nom_restaurant = str(df_offres['nom_restaurant'].iloc[i])
                nouvelle_offre = str(df_offres['offre_actuelle'].iloc[i])
                k.append((user_id, "{} a mis en ligne l'offre suivante: \n{}".format(nom_restaurant, nouvelle_offre)))
    return k

load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')
BOT_USERNAME = os.environ.get('BOT_USERNAME')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Bienvenue! Envoyez-moi le lien de la page Deliveroo ou UberEats du restaurant qui vous intéresse.')

user_links = {}
if os.path.exists('df_offres.csv'):
    df_offres = pd.read_csv('df_offres.csv')
else:
    df_offres = pd.DataFrame(columns=['user_id', 'url_restaurant', 'nom_restaurant', 'offre_t-1', 'offre_actuelle'])

async def save_user_link(update: Update, context: CallbackContext) -> None:
    if update.message.text.startswith("https://deliveroo.fr/") or update.message.text.startswith("https://www.ubereats.com/fr/"):
        user_id = update.message.from_user.id
        user_links[user_id] = update.message.text
        await update.message.reply_text(text='Alerte programmée... Pensez à activer les notifications Telegram!')
        context.job_queue.run_repeating(new_offer_alert, 30)
    else:
        await update.message.reply_text('Veuillez envoyer un lien Deliveroo ou UberEats valide.')

async def new_offer_alert(context: CallbackContext) -> None:
    global user_links, df_offres
    df_offres = save_and_update_offre(user_links, df_offres)
    k = detect_offre(df_offres)
    if k:
        print('Nouvelle offre detectée')
        for i in k:
            user = i[0]
            alert = i[1]
            await context.bot.send_message(chat_id=user, text=alert)
    else:
        print('Pas de nouvelle offre')

async def stop_alerts(update: Update, context: CallbackContext) -> None:
    global user_links, df_offres
    user_id = update.message.from_user.id
    if user_id in df_offres['user_id'].unique():
        restaurants = [df_offres['nom_restaurant'].iloc[i] for i in range(len(df_offres)) if df_offres['user_id'].iloc[i] == user_id]
        buttons = [InlineKeyboardButton(restaurant, callback_data=restaurant) for restaurant in restaurants]
        buttons.append(InlineKeyboardButton('Tous les restaurants', callback_data='all'))
        keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Sélectionnez les restaurants pour lesquels vous souhaitez arrêter les alertes:',
                                        reply_markup=reply_markup)
    else:
        await update.message.reply_text('Vous ne recevez actuellement aucune alerte. '
                                      'Si vous le souhaitez, envoyez un lien Deliveroo ou UberEats.')

async def stop_alerts_callback(update: Update, context: CallbackContext) -> None:
    global user_links, df_offres, headers
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    if query.data == 'all':
        del user_links[user_id]
        df_offres.drop(df_offres[df_offres.user_id == user_id].index, inplace=True)
        await query.edit_message_text('Vous ne recevrez plus d\'alertes. '
                                    'Si vous souhaitez reprendre, envoyez un lien Deliveroo ou UberEats.')
    else:
        restaurant_name = str(query.data)
        user_links = {key:val for key, val in user_links.items() if recuperer_nom(val, headers) != restaurant_name}
        df_offres.drop(df_offres[(df_offres.user_id == user_id) & (df_offres.nom_restaurant == restaurant_name)].index, inplace=True)
        await query.edit_message_text(f'Vous ne recevrez plus d\'alertes pour {restaurant_name}.')

        
if __name__ == '__main__':
    print('Starting bot...')
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_link))
    app.add_handler(CommandHandler('stop', stop_alerts))
    app.add_handler(CallbackQueryHandler(stop_alerts_callback))
    app.run_polling(poll_interval=3)
    print(user_links)