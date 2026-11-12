# Conversations and interventions

Create a network, edit the staged texts, then start execution. An exchange has one forward message and one reply. Three senders, one receiver and five exchanges using all-to-one pairing produce three conversations and 30 transmissions. All-to-one selects the first receiver. One-to-all selects the first sender. One-to-one requires equal counts. Random pairing samples distinct pairs without replacement.

Each conversation advances independently. The next exchange waits for the preceding reply to reach its sender’s device. The reply address comes from the decrypted content. The device log records outgoing submissions, received ciphertext and locally decrypted text. A terminal delivery failure stops that conversation. Other conversations continue.

A disabled receiver keeps its pending messages at its provider. Re-enabling polling allows its next fixed-period pull to discover them. A path block applies immediately at the current logical timestamp. Existing transits can finish unless the operator explicitly selects **Drop in flight**. An offline destination causes an unresponsive observation. End-to-end retries draw a fresh packet and route within the configured budget.

Step advances one scheduled Python action. Pause holds the logical clock. Playback delay controls the wall-clock wait between actions. A 500-second simulated outage need not take 500 seconds to watch. Reset reconstructs the staged network from its seed and clears runtime logs, interventions and session keys. Cryptographic randomness remains independent of that seed.
