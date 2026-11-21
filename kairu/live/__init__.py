"""Kairu Live in the bar (VOICE.md "Kairu Live", ADR-052 proposed, the owner's GO of 18 Nov 2026).

talk.py is the LiveKit talking program: LiveKit Agents, Deepgram hearing, Gemini thinking, ElevenLabs speaking, on this PC's
own mic and speaker. It imports nothing of Kairu and holds no authority: everything it wants done on the PC is an order it
hands to listener.py, which hands it to the bar, which hands it to the task core and Guardian, like a typed order.

listener.py is the Guardian action live.talk: started by Guardian when you switch the mic on in the bar (voice.live: true in
config.yaml), it says hello on the bar's voice link with the session token, starts talk.py, and relays between them.
relay.py is the bar's side: what Kairu Live is told back about each order.
"""
