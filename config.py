import datetime

BOT_TOKEN = "7811075054:AAHu-f0MGkeTGvlqzbgIBdeLiXBobrNK5vM"

INITIAL_ADMINS = [
    6649448642,
    881760504
]

MANDATORY_CHANNELS = ["sellfrilance", "buyfrilance"]

SELL_CHANNEL = "@sellfrilance"
BUY_CHANNEL  = "@buyfrilance"

SUBSCRIPTION_PRICES = {
    "base": {
        30: 30,   
        90: 80,    
        365: 300  
    },
    "classic": {
        30: 100,
        90: 270,
        365: 1000
    },
    "pro": {
        30: 200,
        90: 540,
        365: 2000
    }
}

PIN_PRICE = 250

PIN_CYCLE_SECONDS = 30 * 24 * 3600
