from dotenv import load_dotenv

load_dotenv()

import marvin


class SmallPlane(marvin.NaturalLangType):
    pass


marvin.match(
    "Alexa turn on the lamp",
    ("Play Music by {artist}", lambda artist: artist),
    ("Volume increase by {volume_up} units", lambda volume_up: volume_up),
    ("Lights on", lambda: True),
    ("Lights off", lambda: True),
    (SmallPlane, lambda small_plane: print(small_plane)),
)

if __name__ == "__main__":
    pass
