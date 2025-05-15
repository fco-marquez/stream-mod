import random

def moderate_message(message):
    if random.random() < 0.3:
        return False, "Profanity"
    return True, None