# Writing style for the learning docs

All files in `docs/learning/` use one style. The style is an adaptation of Simple Technical English (ASD-STE100). Every agent and every session writes to these rules, so that the docs read the same everywhere.

We use the STE writing rules as guidelines, not as strict limits. We do not use the STE dictionary: technical names and our own terms (below) are allowed. These docs do not claim ASD-STE100 compliance.

**Clarity comes first.** If a topic needs a longer explanation, more detail or a longer sentence, write it. The rules below are the default, and a writer can depart from them for a reason. Facts and citations (§4) are the exception: they are always exact.

## 1. Words

1. **Use one word for one meaning.** Use the terms in §5 with the meaning given there. Do not use a synonym for variety.
2. **Write names exactly.** Code, registers, files, commands and properties go in backticks, as the source spells them: `GICD_IIDR`, `realize`, `info mtree -f`.
3. **Use no idioms or figures of speech.** Write "continue", not "carry on". Write "the identification register", not "the nameplate".
4. **Use simple verbs.** Write "use", not "utilize". Write "to", not "in order to". Write "for example" and "that is", not "e.g." and "i.e.".
5. **Use no filler words:** "simply", "just", "basically", "obviously", "really".
6. **Make "it" and "this" clear.** If the noun is not in the same or the previous sentence, write the noun again.

## 2. Sentences

1. **One idea in each sentence.** Do not join two ideas with a semicolon or with "and" when each idea can stand alone.
2. **Keep sentences short.** As a guide, an instruction has approximately 20 words or fewer, and a description approximately 25. Code in backticks counts as one word. A citation in parentheses at the end does not count.
3. **Use the active voice.** Write "QEMU refuses the access", not "the access is refused".
4. **Use the present tense** for what the model and QEMU do. Use the past tense only for what happened in a test run or on the EVK.
5. **Put a condition first.** Write "If the test fails, read the red line", not "Read the red line if the test fails".
6. **Use a list for three or more items.**

## 3. Paragraphs and sections

1. **Start each section with its purpose:** one or two sentences that say what the section shows and why it matters.
2. **One topic in each paragraph.** A paragraph has six sentences or fewer. Give the main fact first.
3. **Give procedures as numbered steps.** Write each step as a command. Give one action in each step, then the result to expect.
4. **Show, then explain.** Give the real output or code first, then say what it means.
5. **Use a table** to compare items that have the same attributes.
6. **Use "Note:"** for information that is not part of the main text. Use one note for one fact.

## 4. Facts and citations

1. **A rewrite does not change facts.** Every code token, number, `file:line` citation and section reference stays the same. Check a rewrite with `scripts/doc-facts.py` (§6).
2. **Cite the source of each fact,** as in AGENTS.md "Sources": the manual by section and page, guest and QEMU code by `file:line`.
3. **Link project files.** Write a project file as a relative Markdown link. For a section of a file, link to its heading. The README gives the conventions.
4. **Give the context of a milestone.** A file about a milestone starts with a context box. The box links the milestone's goal and its unit files.

## 5. Terms

| Term | Meaning in these docs |
|---|---|
| abort | a synchronous external abort: the exception the CPU takes when the bus refuses an access |
| access | one guest load or store to one address |
| board | the QEMU machine for the EVK (`rzv2l-smarc`); the physical board is "the EVK" |
| device | a QEMU object that models one hardware block, for example SYSC |
| EVK | the physical RZ/V2L SMARC board |
| fixup | an edit that QEMU's loader makes to the DTB before the guest starts |
| guest | software that runs inside QEMU |
| hole | an address that no memory region owns |
| host | the PC that runs QEMU |
| model | the QEMU code for the board, the SoC and the devices; "the model" is all of it |
| mutation | a change to the model, made on purpose, that a test must detect |
| property | a setting on a device, chosen before `realize` |
| red / green | the test fails / the test passes |
| region | a QEMU memory region: RAM, MMIO or a container |
| SoC | the chip (R9A07G054) as one QEMU object |

Add a term here before you use it with a new meaning.

## 6. Checks

- `scripts/lint.py style` gives a hint for each sentence that is longer than 25 words, and for each word from §1.3 to §1.5. A hint is not an error. Keep the text as it is if it is clearer that way.
- `scripts/doc-facts.py OLD NEW` compares the facts in two versions of a file. Use it for each rewrite. It lists each code token, number, ID (`M1-T04`, `EL1`), page, citation and section reference that is in one version only. It compares sets: it does not see a fact that moves to another place, or a lost qualifier such as "only" or "not". Read each changed sentence too.

The style hints are advisory. The facts check is not: a difference in facts must be a mistake to fix or a deliberate change to name. A reviewer reads the text too.

## 7. Example

Before:

> Holes are where honesty matters (AGENTS.md rule 6, "never silently wrong"). An unassigned address is backed by QEMU's `io_mem_unassigned` region, whose `accepts` callback refuses every access.

After:

> A hole is an address that no region owns. The model must not hide a hole (AGENTS.md rule 6). QEMU puts the region `io_mem_unassigned` behind each hole. The `accepts` callback of this region refuses all accesses.
