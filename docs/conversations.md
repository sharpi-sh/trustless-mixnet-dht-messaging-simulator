# Conversations and interventions

Create a network, edit the staged texts, then start execution. An exchange has one forward message and one reply. Three senders, one receiver and five exchanges using all-to-one pairing produce three conversations and 30 transmissions. All-to-one selects the first receiver. One-to-all selects the first sender. One-to-one requires equal counts. Random pairing samples distinct pairs without replacement.

Each conversation advances independently. The next exchange waits for the preceding reply to reach its sender’s device. The receiving device verifies the signed message against the sender’s pinned Ed25519 public key before accepting its text or using its X25519 reply address. The device log records outgoing submissions, received ciphertext and locally decrypted text. A terminal delivery failure stops that conversation. Other conversations continue.

A disabled receiver keeps its pending messages at its provider. Re-enabling polling allows its next fixed-period pull to discover them. A path block applies immediately at the current logical timestamp. Existing transits can finish unless the operator explicitly selects **Drop in flight**. An offline destination causes an unresponsive observation. End-to-end retries draw a fresh packet and route within the configured budget.

Step advances one scheduled Python action. Pause holds the logical clock. During ordinary playback, the delay controls the wall-clock pause for visible message activity while the scheduler advances through intervening protocol traffic. A 500-second simulated outage need not take 500 seconds to watch. Reset reconstructs the staged network from its seed and clears runtime logs, interventions and session keys. Cryptographic randomness remains independent of that seed.


The conversation reaches completion when every planned forward and reply has reached its terminal outcome. The final snapshot retains the logical clock and any background polling, cover or maintenance work that was outstanding at that instant. In the event timeline, open a route-construction event and choose **Show recorded route** to inspect its packet path. **Clear recorded route** returns the graph to live selection.
