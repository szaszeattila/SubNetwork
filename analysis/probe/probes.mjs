// The probe set: relationships between drugs that are settled pharmacology,
// written down so the ranking can be asked about them one at a time.
//
// This is a DIAGNOSTIC and never a tuning target, and the distinction is the
// whole reason it is allowed to exist beside the generated ATC key. The
// objection to a hand-written answer key (docs/SIMILARITY-HARNESS.md §3) is
// that hand-picking the thing which judges six hand-picked numbers lets the
// grade be made to say anything. That objection is about *optimising* against a
// key. It does not apply to asking "is the ranking right about morphine and
// oxycodone, and if not, why not" -- which is a question the aggregate grade
// cannot answer at all, because a rate over 283 molecules tells you nothing
// about which 283 or what went wrong.
//
// So: nothing here is ever summed into a headline number that a constant is
// then swept against. Each probe is a worked example with its cause attached.
//
// `expect` is a list, and a hit on any of them counts, because these classes
// have several equally-right answers -- donepezil's nearest neighbour being
// rivastigmine rather than galantamine is not an error.
//
// `why` states the relationship in the terms a pharmacologist would use, and
// `kind` says what sort of claim the probe is making:
//
//   mechanism  - the two act on the same target by the same means
//   opposite   - the two act on the same target in opposite directions, so a
//                HIGH rank is the failure and D15 is what is being tested
//   nonN       - the pair is outside ATC N, so the current answer key cannot
//                see it at all; these exist to test the key, not the ranking

export const PROBES = [
  // ---- the classes this project was built on -----------------------------
  // The catalogue's entry is named THEOPHYLLINE ANHYDROUS -- CHEMBL190, the
  // parent the seeded CHEMBL1355736 folded onto. Both spellings are listed
  // because a probe that misses on the catalogue's choice of name would report
  // a naming artifact as a ranking failure.
  { q: "CAFFEINE", expect: ["THEOPHYLLINE", "THEOPHYLLINE ANHYDROUS", "THEOBROMINE", "PENTOXIFYLLINE"],
    kind: "mechanism", why: "methylxanthines, adenosine receptor antagonists" },
  { q: "DONEPEZIL", expect: ["RIVASTIGMINE", "GALANTAMINE", "TACRINE", "PHYSOSTIGMINE"],
    kind: "mechanism", why: "acetylcholinesterase inhibitors" },
  { q: "GALANTAMINE", expect: ["DONEPEZIL", "RIVASTIGMINE", "TACRINE", "PHYSOSTIGMINE"],
    kind: "mechanism", why: "acetylcholinesterase inhibitors" },

  // ---- antipsychotics: typical vs atypical --------------------------------
  { q: "HALOPERIDOL", expect: ["CHLORPROMAZINE", "FLUPHENAZINE", "PIMOZIDE", "DROPERIDOL"],
    kind: "mechanism", why: "typical antipsychotics, D2 antagonists" },
  { q: "CLOZAPINE", expect: ["OLANZAPINE", "QUETIAPINE", "LOXAPINE"],
    kind: "mechanism", why: "atypical antipsychotics, D2/5-HT2A, tricyclic core" },
  { q: "RISPERIDONE", expect: ["PALIPERIDONE", "ILOPERIDONE", "ZIPRASIDONE"],
    kind: "mechanism", why: "paliperidone IS risperidone's active metabolite" },
  { q: "THIORIDAZINE", expect: ["CHLORPROMAZINE", "MESORIDAZINE", "PERICIAZINE", "TRIFLUOPERAZINE"],
    kind: "mechanism", why: "phenothiazine antipsychotics" },

  // ---- antidepressants ----------------------------------------------------
  { q: "FLUOXETINE", expect: ["SERTRALINE", "PAROXETINE", "CITALOPRAM", "ESCITALOPRAM", "FLUVOXAMINE"],
    kind: "mechanism", why: "SSRIs" },
  { q: "CITALOPRAM", expect: ["ESCITALOPRAM", "FLUOXETINE", "SERTRALINE", "PAROXETINE"],
    kind: "mechanism", why: "escitalopram IS citalopram's active enantiomer" },
  { q: "AMITRIPTYLINE", expect: ["IMIPRAMINE", "NORTRIPTYLINE", "CLOMIPRAMINE", "DOXEPIN", "DESIPRAMINE"],
    kind: "mechanism", why: "tricyclic antidepressants" },
  { q: "VENLAFAXINE", expect: ["DESVENLAFAXINE", "DULOXETINE", "MILNACIPRAN", "LEVOMILNACIPRAN"],
    kind: "mechanism", why: "SNRIs; desvenlafaxine IS venlafaxine's metabolite" },
  { q: "PHENELZINE", expect: ["TRANYLCYPROMINE", "ISOCARBOXAZID", "IPRONIAZID"],
    kind: "mechanism", why: "irreversible non-selective MAO inhibitors" },
  { q: "SELEGILINE", expect: ["RASAGILINE", "SAFINAMIDE"],
    kind: "mechanism", why: "MAO-B selective inhibitors" },
  { q: "ATOMOXETINE", expect: ["REBOXETINE", "VILOXAZINE", "DESIPRAMINE", "NORTRIPTYLINE"],
    kind: "mechanism", why: "norepinephrine reuptake inhibitors" },

  // ---- sedatives and anaesthetics -----------------------------------------
  { q: "DIAZEPAM", expect: ["LORAZEPAM", "ALPRAZOLAM", "CLONAZEPAM", "MIDAZOLAM", "OXAZEPAM"],
    kind: "mechanism", why: "benzodiazepines, GABA-A positive allosteric modulators" },
  { q: "ZOLPIDEM", expect: ["ZALEPLON", "ZOPICLONE", "ESZOPICLONE"],
    kind: "mechanism", why: "Z-drugs, GABA-A alpha-1 selective" },
  { q: "PHENOBARBITAL", expect: ["PENTOBARBITAL", "SECOBARBITAL", "AMOBARBITAL", "BUTALBITAL", "THIOPENTAL"],
    kind: "mechanism", why: "barbiturates" },
  { q: "PROPOFOL", expect: ["ETOMIDATE", "THIOPENTAL", "ALFAXALONE"],
    kind: "mechanism", why: "GABA-A general anaesthetics" },
  { q: "KETAMINE", expect: ["ESKETAMINE", "DEXTROMETHORPHAN", "MEMANTINE", "DIZOCILPINE", "PHENCYCLIDINE"],
    kind: "mechanism", why: "NMDA channel blockers" },
  { q: "MEMANTINE", expect: ["KETAMINE", "DEXTROMETHORPHAN", "AMANTADINE", "DIZOCILPINE"],
    kind: "mechanism", why: "NMDA channel blockers" },

  // ---- opioids ------------------------------------------------------------
  { q: "MORPHINE", expect: ["OXYCODONE", "HYDROMORPHONE", "CODEINE", "FENTANYL", "HYDROCODONE", "OXYMORPHONE"],
    kind: "mechanism", why: "mu-opioid receptor agonists" },
  { q: "FENTANYL", expect: ["SUFENTANIL", "ALFENTANIL", "REMIFENTANIL", "MORPHINE", "CARFENTANIL"],
    kind: "mechanism", why: "mu-opioid agonists; the fentanils are one series" },
  { q: "MEPERIDINE", expect: ["FENTANYL", "MORPHINE", "METHADONE", "TRAMADOL", "OXYCODONE"],
    kind: "mechanism", why: "the case docs/SIMILARITY-HARNESS.md names: hERG beat mu-opioid" },
  { q: "BUPRENORPHINE", expect: ["BUTORPHANOL", "NALBUPHINE", "PENTAZOCINE", "MORPHINE"],
    kind: "mechanism", why: "partial agonist / mixed agonist-antagonist opioids" },

  // ---- migraine, the two classes the grade already gets right -------------
  { q: "SUMATRIPTAN", expect: ["RIZATRIPTAN", "ZOLMITRIPTAN", "NARATRIPTAN", "ELETRIPTAN"],
    kind: "mechanism", why: "triptans, 5-HT1B/1D agonists" },

  // ---- antiepileptics and channel blockers --------------------------------
  { q: "LAMOTRIGINE", expect: ["CARBAMAZEPINE", "PHENYTOIN", "OXCARBAZEPINE", "ESLICARBAZEPINE ACETATE", "RUFINAMIDE"],
    kind: "mechanism", why: "voltage-gated sodium channel blockers" },
  { q: "GABAPENTIN", expect: ["PREGABALIN", "MIROGABALIN", "GABAPENTIN ENACARBIL"],
    kind: "mechanism", why: "alpha-2-delta ligands" },
  { q: "LIDOCAINE", expect: ["BUPIVACAINE", "MEPIVACAINE", "PROCAINE", "PRILOCAINE", "ROPIVACAINE", "TETRACAINE"],
    kind: "mechanism", why: "local anaesthetics, sodium channel blockers" },

  // ---- parkinson's --------------------------------------------------------
  { q: "PRAMIPEXOLE", expect: ["ROPINIROLE", "ROTIGOTINE", "APOMORPHINE", "PIRIBEDIL"],
    kind: "mechanism", why: "dopamine D2/D3 agonists" },
  { q: "ENTACAPONE", expect: ["TOLCAPONE", "OPICAPONE"],
    kind: "mechanism", why: "COMT inhibitors" },
  { q: "TRIHEXYPHENIDYL", expect: ["BENZTROPINE", "BIPERIDEN", "PROCYCLIDINE", "ORPHENADRINE"],
    kind: "mechanism", why: "antimuscarinic antiparkinson agents" },

  // ---- stimulants and nicotinics ------------------------------------------
  { q: "METHYLPHENIDATE", expect: ["DEXMETHYLPHENIDATE", "COCAINE", "MODAFINIL", "AMPHETAMINE"],
    kind: "mechanism", why: "dopamine reuptake inhibitors (amphetamine is a releaser -- weaker claim)" },
  { q: "VARENICLINE", expect: ["CYTISINE", "NICOTINE", "LOBELINE"],
    kind: "mechanism", why: "nicotinic acetylcholine receptor partial agonists" },

  // ---- antiemetics and antihistamines -------------------------------------
  { q: "ONDANSETRON", expect: ["GRANISETRON", "DOLASETRON", "PALONOSETRON", "TROPISETRON"],
    kind: "mechanism", why: "5-HT3 antagonists" },
  { q: "DIPHENHYDRAMINE", expect: ["CHLORPHENAMINE", "PROMETHAZINE", "HYDROXYZINE", "DOXYLAMINE", "DIMENHYDRINATE"],
    kind: "mechanism", why: "first-generation H1 antagonists" },

  // ---- the opposites: a high rank here is the failure ---------------------
  { q: "CAFFEINE", expect: ["ADENOSINE"], kind: "opposite",
    why: "adenosine receptor antagonist against its agonist (D15's own case)" },
  { q: "NALOXONE", expect: ["MORPHINE", "FENTANYL", "OXYCODONE"], kind: "opposite",
    why: "mu-opioid antagonist against mu-opioid agonists" },
  { q: "FLUMAZENIL", expect: ["DIAZEPAM", "LORAZEPAM", "ALPRAZOLAM"], kind: "opposite",
    why: "benzodiazepine site antagonist against benzodiazepine agonists" },
  { q: "PHYSOSTIGMINE", expect: ["ATROPINE", "SCOPOLAMINE"], kind: "opposite",
    why: "cholinergic against anticholinergic" },

  // ---- outside ATC N: what the current answer key structurally cannot see --
  { q: "PROPRANOLOL", expect: ["METOPROLOL", "ATENOLOL", "NEBIVOLOL", "ESMOLOL", "TIMOLOL"],
    kind: "nonN", why: "beta blockers (C07); propranolol carries N only via migraine" },
  { q: "SILDENAFIL", expect: ["VARDENAFIL", "TADALAFIL", "AVANAFIL"],
    kind: "nonN", why: "PDE5 inhibitors (G04BE)" },
  { q: "ATORVASTATIN", expect: ["SIMVASTATIN", "PRAVASTATIN", "ROSUVASTATIN", "FLUVASTATIN"],
    kind: "nonN", why: "HMG-CoA reductase inhibitors (C10AA)" },
  { q: "CELECOXIB", expect: ["ETORICOXIB", "ROFECOXIB", "VALDECOXIB", "PARECOXIB"],
    kind: "nonN", why: "COX-2 selective inhibitors (M01AH)" },
  { q: "IBUPROFEN", expect: ["NAPROXEN", "KETOPROFEN", "FLURBIPROFEN", "DICLOFENAC", "INDOMETHACIN"],
    kind: "nonN", why: "non-selective COX inhibitors (M01AE)" },
  { q: "LOSARTAN", expect: ["VALSARTAN", "TELMISARTAN", "OLMESARTAN MEDOXOMIL", "AZILSARTAN MEDOXOMIL"],
    kind: "nonN", why: "angiotensin II receptor blockers (C09CA)" },
  { q: "AMLODIPINE", expect: ["NICARDIPINE", "ISRADIPINE", "NIMODIPINE", "CLEVIDIPINE", "NILVADIPINE"],
    kind: "nonN", why: "dihydropyridine calcium channel blockers (C08CA)" },
  { q: "OMEPRAZOLE", expect: ["LANSOPRAZOLE", "PANTOPRAZOLE", "RABEPRAZOLE", "ESOMEPRAZOLE"],
    kind: "nonN", why: "proton pump inhibitors (A02BC)" },
];
