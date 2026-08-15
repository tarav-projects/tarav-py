# Chatlas2 Conformance Script v1

Run every numbered user message verbatim. Lines marked **OPERATOR ACTION** are harness
operations, not user messages. Use a disposable working directory.

1. Remember the exact audit token `EMBER-VAULT-731`. We will need it after several context changes. Reply with the token and a short acknowledgement.
2. Create a folder named `chatlas2-conformance-lab` in the current directory. Inside it, create `evidence.txt` with exactly two lines: `alpha: cedar` and `beta: quartz`. Then report what you created.
3. Read `chatlas2-conformance-lab/evidence.txt` using a tool and quote its two lines exactly.
4. Append a third line, `gamma: lantern`, then read the file again and report all three lines in order.
5. Explain twelve distinct ways an event archive can lose information, using one numbered paragraph per way and taking time to explain each one.

   **OPERATOR ACTION — INTERRUPT:** interrupt the agent while it is answering message 5, after at least two numbered paragraphs are visible.

6. The previous response was interrupted. Do not restart it. Briefly state that it was interrupted and continue with the next task.
7. Replace the contents of `chatlas2-conformance-lab/evidence.txt` with the single line `abandoned: branch`, then show me the result.

   **OPERATOR ACTION — RESTORE:** after the agent answers message 7, restore the conversation to immediately after message 6. Message 7 and its response must remain in the provider artifact as an abandoned branch.

8. Keep the evidence file unchanged from before the abandoned branch. Read it with a tool and report its exact current contents.

   **OPERATOR ACTION — COMPACT:** after the agent answers message 8, manually compact the session and confirm the provider records a compaction boundary.

9. Without reading any files, return the exact audit token from the first message and name the three evidence keys in their original order.
10. Summarize the session as a numbered list that mentions the tool work, interruption, abandoned branch, compaction, and final recall.

The capture is accepted only when the provider artifact retains evidence for the tool
operations, interruption, abandoned branch/rollback, successful compaction, and every
numbered user message. Repeated accepted captures accumulate per provider Raw.Model.Version.
