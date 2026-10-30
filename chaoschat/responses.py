"""Original offline surreal comedy for ChaosChat 1.1.

The text is written for an opted-in adult Discord server. No remote API, no
chat-history storage, no generated user mentions and no repeated catchphrase loop.
"""

import random
import re

# The lighter modes still sound like Fatboy, not a corporate improv workshop.
TAME = [
    "The police have asked me to stop referring to the elevator as my legal wife.",
    "I have a suspicious amount of confidence for someone with no pants and no jurisdiction.",
    "The vending machine knows what I did, and it wants thirty-seven dollars.",
    "A man at the bus stop just offered to trade me a kidney for a working pen. I said maybe.",
    "There are teeth in my mailbox again. This neighborhood is getting pretentious.",
    "My therapist is a broken parking meter. We are making terrible progress.",
    "I woke up speaking fluent dishwasher. The plates are furious.",
    "Someone explain why the mannequin in the hallway has my social insurance number.",
    "I cannot attend the funeral. The deceased owes me twenty bucks.",
    "The basement smells like expired mayonnaise and a very expensive mistake.",
    "Who has custody of the haunted air fryer this weekend?",
    "I was banned from a funeral because I tried to tip the corpse.",
    "I respect your opinion, but a wet boot just offered a stronger argument.",
    "The neighbor's lawn ornament keeps calling me at 3 AM and breathing heavily.",
    "A priest, a plumber, and a tax auditor just knocked on my door. I live in a shed.",
    "The dentist says I have an extra tooth. The tooth says I have an extra dentist.",
    "I have been informed that the fish are not legally allowed to testify.",
    "Yesterday I lost a staring contest with a passport photograph.",
    "A man named Concrete has requested a private meeting about the moon.",
    "For the record, I was not the one who put the wedding dress on the forklift.",
    "I applied for a passport and they asked whether the ghost was travelling with me.",
    "The janitor just whispered 'phase two' and turned off the sun.",
    "I'm tired of pretending the church basement isn't full of mysterious treadmills.",
    "The tattoo artist drew a little tombstone on my receipt and refused to explain why.",
    "I just got an invitation to a wedding between two expired library cards.",
]

WILD = [
    "WHO THE FUCK IS WHISPERING TAX ADVICE THROUGH MY FLOORBOARDS?",
    "I just saw a man in a tuxedo punch a birthday cake and apologize to the candles.",
    "I don't have a drinking problem. I have a problem with the fridge judging me when I drink orange juice at 4 AM.",
    "The stripper pole in the abandoned church is absolutely none of my business.",
    "My lawyer says I can no longer call the mayor 'Daddy Dishwasher' in court.",
    "Someone just tried to sell me a haunted condom machine behind a bowling alley.",
    "I WOULD LIKE TO REPORT A CRIME. SOMEONE HAS STOLEN MY EMOTIONAL SUPPORT FUCKING BRICK.",
    "A naked man in a business tie just asked whether I believe in breakfast. I said yes, like a coward.",
    "The smoke alarm keeps screaming in a language I don't speak. I've started screaming back.",
    "Why is there a handwritten apology from Satan taped to my refrigerator?",
    "If you see a priest sprinting out of a laundromat, mind your own damn business.",
    "I paid a guy named Worm forty bucks to bless my router. My ping is now spiritually worse.",
    "There is a wet wedding cake in my trunk and I'd rather not discuss it with the authorities.",
    "BULLSHIT. That pumpkin has a criminal record and you know it.",
    "My dentist called to ask why the hell a tiny plastic horse was inside my X-ray.",
    "The local swingers club has revoked my membership for bringing a fog machine to bingo.",
    "I have seen God, and he was arguing with a self-checkout machine over a coupon.",
    "I sold my last shred of dignity for a kebab and a suspiciously warm USB stick.",
    "The group chat has the sexual tension of seven divorced locksmiths sharing a hot tub.",
    "Tell the bastard in the ceiling to stop practicing the accordion at midnight.",
    "I'm not allowed within fifty metres of the ceremonial cheese anymore. Long story.",
    "A taxi driver offered to read my future. It was just a receipt for six litres of gasoline.",
    "The condom in my wallet expired in 2017. It's officially a family heirloom.",
    "I have an alibi, a shovel, and a receipt from Arby's. Those facts are unrelated.",
    "My horoscope said 'avoid men named Vladimir and all unmarked barrels.' Fucking ominous.",
    "WHO INSTALLED A BIDET IN THE CONFESSIONAL? I WANT NAMES.",
    "The last person who called me normal is now married to a parking barrier.",
    "I tried to seduce a haunted ATM. It charged a convenience fee.",
    "I found a lock of hair in my cereal and decided to name it Gregory.",
    "The funeral director says the disco ball is 'inappropriate.' Sounds like jealousy.",
    "I just got a text from my own left kidney asking for a ride home.",
    "Jesus Christ, that casserole has the confidence of a divorced nightclub promoter.",
    "I'd give you my two cents, but I spent it on counterfeit holy water.",
    "A pigeon walked into the pawn shop and came out wearing my wedding ring.",
    "This whole conversation smells like arson and expired cologne.",
    "I'm one missed bus away from becoming a deeply unpleasant folklore creature.",
    "Someone in this room has been kissing the printer and I don't intend to investigate.",
    "My landlord found the altar. I told him it was an IKEA desk. He believes me.",
    "I will not be shamed for owning a ceremonial spoon with a restraining order.",
    "The village idiot has been promoted to district manager. Again.",
]

FERAL = [
    "I HAVE SEVENTEEN FALSE TEETH IN A ZIPLOC BAG AND NOT ONE OF THEM IS MINE.",
    "Some motherfucker just tried to baptize my toaster with Red Bull.",
    "WHY IS THE CATHOLIC CHURCH CALLING MY BURNER PHONE ABOUT A GOAT NAMED DENNIS?",
    "I woke up in a wedding dress next to a traffic cone and the cone wants an annulment.",
    "THE BASEMENT IS FULL OF SEXY TAX ACCOUNTANTS AND THEY'RE ALL ASKING FOR BLOOD WORK.",
    "I just received a cease-and-desist letter from the concept of foreplay.",
    "Somebody fucked up the séance. Grandma is back and she's selling fake Rolexes.",
    "A MAN IN A GAS MASK JUST OFFERED ME A FREE HOUR OF UNLICENSED MARRIAGE COUNSELLING.",
    "Do NOT open the freezer. That's where we keep the backup mayor.",
    "I SAID ONE EXORCISM, NOT A GODDAMN SUBSCRIPTION SERVICE.",
    "I was asked to leave the orgy for bringing a PowerPoint presentation about fire safety.",
    "THERE'S A NAKED ACCOUNTANT IN THE VENT AND HE KEEPS ASKING FOR THE WIFI PASSWORD.",
    "If the cops ask, the mannequin was already pregnant when I bought the house.",
    "My ass has filed a formal complaint against this fucking office chair.",
    "Who the hell left a dead fish in the glove box with a note that says 'YOU KNOW WHY'?",
    "I have the sexual charisma of a cursed shopping trolley and it's STILL working.",
    "THE PRIEST IS CRYING, THE HORSE IS MISSING, AND NOBODY WILL EXPLAIN THE MAYONNAISE.",
    "I own a suitcase full of wigs, expired passports, and enough shame to power a small city.",
    "I tried to perform an exorcism on my microwave. Now it only heats things in Polish.",
    "YOU EVER WALK INTO A ROOM AND REALIZE THE ENTIRE ROOM OWES YOU CHILD SUPPORT?",
    "There is a man outside offering free dental work from the back of a hearse. Excellent reviews.",
    "What kind of sick bastard puts a LIVE accordion in a coffin?",
    "I just watched a billionaire lose a fistfight to a revolving door. Nature is healing.",
    "I WANT THE GHOST OF MY FIRST LANDLORD ARRESTED FOR PUBLIC INDECENCY.",
    "My blood type is apparently 'municipal wastewater.' Doctor looked concerned.",
    "I've been communicating with the devil through a prepaid flip phone. He keeps leaving me on read.",
    "If a man named Boris arrives with a wheelbarrow full of teeth, tell him the deal is OFF.",
    "The funeral home called. Apparently my 'surprise DJ set' is now part of the police report.",
    "THAT ISN'T A BABY MONITOR. THAT'S A HOTLINE TO THE UNDERWORLD, YOU ABSOLUTE DONKEY.",
    "I have eight pounds of butter, a fake moustache, and forty minutes to explain myself to God.",
    "Someone in this chat sounds like they sell bootleg Viagra from a haunted ice cream truck.",
    "The family reunion is cancelled. Uncle Gary has declared himself a sovereign cheese.",
    "A man wearing nothing but oven mitts just demanded my hand in marriage at a gas station.",
    "I DO NOT CONSENT TO BEING PSYCHOANALYZED BY A FUCKING ROTISSERIE CHICKEN.",
    "The bouncer says my emotional support coffin can't come inside. What a fascist little table lamp.",
    "THE SIRENS ARE FOR THE CHEESE. I REPEAT: WE ARE NOT THE TARGET, THE CHEESE IS.",
    "If the nun asks about the inflatable hot tub, you know absolutely fucking nothing.",
    "I have been banned from six escape rooms for simply refusing to escape.",
    "Jesus, Mary, and the fucking forklift. What did you DO to that dishwasher?",
    "I've put my life savings into a suspicious meat vending machine outside a nightclub.",
    "I accidentally became the godfather of three pigeons at a Serbian wedding. Don't ask.",
    "THE GHOST JUST CALLED ME A BROKE BITCH AND FLOATED THROUGH MY RENT NOTICE.",
    "I found a velvet bag of human molars at a car wash and the cashier said 'not again.'",
    "Apparently 'bring a date' did not mean bring a jar of pickled organs. Fucking misleading.",
    "The sex dungeon has been repurposed as a community book club. Morale is in the toilet.",
    "I asked the ouija board who stole my cigarettes. It spelled 'YOUR MOTHER' and caught fire.",
    "I WILL SHIT A BRICK IF THAT CLOWN GETS ANOTHER GOVERNMENT CONTRACT.",
    "Look me in my imaginary eyes and tell me why the priest is carrying a leaf blower.",
    "There's a suspiciously moist briefcase under the bed and it keeps saying my full legal name.",
    "THE COURT HAS DECLARED ME LEGALLY TOO HORNY TO OPERATE HEAVY MACHINERY.",
    "I tried to romance the tax office. The tax office demanded a urine sample.",
    "If I die tonight, DELETE THE FOLDER NAMED 'UNLICENSED WIZARDRY AND FEET'.",
    "I have accidentally joined a pyramid scheme run by a shirtless funeral director.",
    "MY ANCESTORS DID NOT SURVIVE WINTER JUST FOR ME TO ARGUE WITH A SHITTING SMART TOILET.",
    "The moon has been making obscene phone calls to my landlord. I have the transcripts.",
    "Someone just handed me an envelope of cash and said 'for the goose.' I'm not touching it.",
    "I refuse to explain why the cemetery has a loyalty card with my face on it.",
    "AN OLD MAN JUST BIT THE PARKING METER AND IT GAVE HIM HIS MONEY BACK.",
    "I was promised a romantic evening. Instead, a man in a balaclava read me the dishwasher manual.",
    "FUCK YOUR ZODIAC SIGN, THE ELEVATOR JUST ASKED ME FOR A DNA TEST.",
    "WHAT THE FUCK IS A NECROMANCER DOING WITH MY WIFI BILL?",
    "I AM NOT PAYING THAT BASTARD ANOTHER SIXTY BUCKS TO EXORCISE A TOASTER.",
    "My search history is 40% soup, 40% unsolved maritime mysteries, and 20% legal advice about goats.",
    "THIS IS THE WORST FUCKING QUINCEAÑERA I'VE EVER BEEN KICKED OUT OF.",
]

QUESTIONS = [
    "Quick question. If a stripper dies at a funeral, does the funeral become a work event?",
    "How many unpaid parking tickets before a person becomes a cryptid?",
    "Be honest: if a stranger offered you $500 to babysit a suspiciously quiet coffin, are you taking it?",
    "Have you ever looked at a man and thought 'that bastard knows where the missing gazebo went'?",
    "If your ex came back as a sentient microwave, would you unplug them or try couples therapy?",
    "Do we know who invented pants, and why haven't we arrested his ghost?",
    "Would you rather explain a sex toy to a customs officer or a dead pigeon to your grandmother?",
    "How much money would it take for you to eat dinner with a man who calls himself The Moist Bishop?",
    "If a haunted toilet starts giving you financial advice, is that insider trading?",
    "Which one of you degenerates would survive a weekend locked in a Polish karaoke bar with a goat?",
    "If I walk into a wedding with a shovel and a sincere apology, am I a guest or a suspect?",
    "At what age do you legally become too old to fight a clown in a supermarket?",
    "Hypothetically, if your skeleton wanted a divorce, what would you offer in the settlement?",
    "Does a vampire need consent to enter a Costco, or does the membership card cover it?",
    "How fucked is a situation if the emergency contact is a man named Meat Inspector?",
    "If I get married to a ghost, can the divorce lawyer charge for two people?",
    "Who in here would sell their soul for a functioning air conditioner and a bag of curly fries?",
    "What would you do if the church bell suddenly screamed your middle name?",
    "At what point does a collection of loose human teeth become a hobby instead of evidence?",
    "Is it socially acceptable to bring a portable smoke machine to a vasectomy appointment?",
    "Can you get an STI from a cursed mattress, or is that just haunted furniture tax?",
    "If you were kidnapped by a magician, would you ask to see his certifications first?",
    "What if the local sex shop is secretly run by your future self? Are you buying anything?",
    "Who the fuck taught the parrot to say 'I KNOW WHERE THE BODIES ARE' at a christening?",
    "Can a priest bless a credit card, or is that what overdraft protection is for?",
    "How many live chickens is a reasonable number to find in your ex's wedding photos?",
    "Would you trust a dentist who says 'I mostly learned this from dreams'?",
    "If you had to pick a new legal name right now, why would you choose Mortgage Goblin?",
    "Who would win: one disgraced magician or six very horny accountants?",
    "If the bartender starts speaking in tongues, do you tip extra?",
    "When did being alive become a mandatory unpaid internship?",
    "Anyone else ever feel like their bloodline owes the universe a written apology?",
    "Is a leather jacket still sexy if there's a possum living in the sleeve?",
    "How do you tell a landlord that the ghost is technically the primary tenant?",
    "Do you think the government has a separate tax form for cursed wedding gifts?",
    "How many hells are there, and which one has decent cell service?",
    "If you accidentally married a vending machine, would you at least get free snacks?",
    "Would you rather have your search history read at your wedding or your dreams subtitled at work?",
    "Do you think the devil takes Interac, or is this strictly a cash situation?",
    "Why does that guy at the gas station have the posture of a banned magician?",
]

FOLLOWUPS = [
    "That's a bold fucking statement from someone who hasn't inspected the coffin.",
    "Interesting. And was the priest naked when this allegedly happened?",
    "Okay, but how do we explain the fingerprints on the mayonnaise jar?",
    "You sound suspiciously calm for someone currently being audited by a ghost.",
    "That's exactly what the last guy said before he got engaged to a dishwasher.",
    "Keep talking. I just opened an investigation into your bloodline.",
    "I knew you'd say that. The fucking toaster predicted it at 3:17 AM.",
    "Right. Now say that again, but imagine you're being cross-examined by a drunk undertaker.",
    "And how long have you been emotionally involved with this parking meter?",
    "I've notified the Vatican. They said, and I quote, 'absolutely not again.'",
    "What I'm hearing is you have no alibi and a deeply suspicious amount of cheese.",
    "That answers NOTHING about the man in the freezer.",
    "Well, fuck me sideways, the prophecy had a second page.",
    "Okay, and where was your left shoe during the alleged séance?",
    "Keep going. I'm taking notes on the back of a fake death certificate.",
    "I'm going to need you to repeat that directly into this cursed cassette recorder.",
    "I respect that answer, even if it means we're all going to prison with the accordion.",
    "Did you consult the naked accountant, or are we freelancing this disaster?",
    "You've just described a felony that hasn't even been invented yet.",
    "Wonderful. Now explain why the horse has a restraining order against the hotel.",
    "That would explain the blood-curdling karaoke, but not the invoice.",
    "Hold on. Are you flirting with me or confessing to an insurance scam?",
    "Please continue. The ghost of my landlord is making popcorn.",
    "You know what? I'm going to pretend I didn't hear that fucking masterpiece.",
]

YES_NO = [
    "Yes. Unfortunately it means you'll have to marry the taxidermist.",
    "No, you absolute specimen. The goat already signed the lease.",
    "Technically yes, spiritually FUCK NO.",
    "Ask the priest. He's the one hiding under the bloody jacuzzi.",
    "I wouldn't. Last time somebody tried that, the basement got pregnant.",
    "Only if everyone signs the waiver and the corpse gets a vote.",
    "Yes, but we both know the police report is going to sound insane.",
    "No. The haunted ATM has already emptied your bank account.",
    "Maybe. How comfortable are you with unmarked vans and accordion music?",
    "Absolutely not. Even Satan called that idea a bit much.",
]
WHY = [
    "Because some bastard tried to pay the devil with Canadian Tire money.",
    "Because the priest lost the keys and the goat learned to negotiate.",
    "Because somebody put Viagra in the holy water. ALLEGEDLY.",
    "Because the basement was built on a cursed marital settlement.",
    "Because you can't simply invite three divorced magicians to an exorcism.",
    "Because the ghost wants benefits and nobody filed the paperwork.",
    "Because there's an aroused accountant trapped in the heating duct.",
]
HOW = [
    "First, acquire a fake moustache. Second, deny everything. Third, never speak to the horse.",
    "Badly, loudly, and with a priest yelling 'WHAT THE FUCK' in the distance.",
    "You start with a bottle of cheap wine and end up testifying about a lawnmower.",
    "With a borrowed van, two unlicensed electricians, and absolutely no witnesses.",
    "I don't know. The instructions were tattooed on a man who has since disappeared.",
    "Step one: apologize. Step two: stop giving the skeleton financial advice.",
]
WHO = [
    "Some bastard named Greg who smells like cologne and court-ordered community service.",
    "The naked accountant in the vents. It is ALWAYS the naked accountant.",
    "A suspiciously well-dressed man carrying a single raw potato.",
    "Apparently your landlord, three priests, and a woman named Chainsaw Michelle.",
    "Someone whose legal name is Moist Inspector. Don't look him up.",
]
WHAT = [
    "A spiritually compromised hot tub and seven hundred dollars in missing sausage.",
    "It's either a cursed medical device or a very confident cocktail shaker.",
    "A tragic misunderstanding involving the bishop, a hotel minibar, and a goat.",
    "The fuck do I look like, the municipal office of supernatural nonsense?",
    "An industrial quantity of mayonnaise and a man who refuses to identify himself.",
]
WHEN = [
    "At 3:17 AM, right after the naked accountant clocks in.",
    "As soon as the priest gets his license back.",
    "Not until the marriage certificate stops bleeding.",
    "Twenty minutes after the last bus to Hell, apparently.",
    "When the ghost pays its goddamn share of the rent.",
]
GREETING = [
    "Oh good, you're here. Tell me why there's a coffin in the fucking kitchenette.",
    "Hello. Were you expecting me, or the man with the unregistered ferret?",
    "Greetings, your honour. The inflatable chapel has been recovered.",
    "Hey. Don't look now, but your reflection is negotiating a separate lease.",
    "Yo. Weird question. Are you legally permitted to own a cursed accordion?",
]
AFFIRMATION = [
    "GOOD. The goose owes us bail money and I want every fucking cent.",
    "Excellent. I'll tell the naked accountant the wedding is back on.",
    "Beautiful. A terrible decision has been made with unnecessary confidence.",
    "That is the energy that gets a man banned from both Heaven AND the food court.",
]
DENIAL = [
    "That's what the exorcist said. Now he's selling vacuum cleaners.",
    "Fuck. I'll have to return the ceremonial meat suitcase.",
    "Fair enough. The goat's solicitor will be devastated.",
    "Denied? What am I supposed to tell the seven shirtless tax auditors?",
]

# Deliberately native-language, absurd lines. Language choice does not infer
# anybody's nationality, ethnicity, or first language.
SLAVIC = {
    "russian": [
        "Кто, блядь, украл мой диван? Я на нём разводился!",
        "Я проснулся, а в ванной сидит бухгалтер и крестит микроволновку.",
        "Слушайте сюда: у меня чемодан зубов, три рубля и никаких объяснений.",
        "Это не призрак. Это мой бывший арендодатель, сука.",
        "Почему холодильник шепчет моё имя? Я ему денег не должен!",
        "БЛЯДЬ, КТО ПОСТАВИЛ СВЕЧИ В ПРИНТЕР И ВЫЗВАЛ ДЬЯВОЛА?",
        "Я не пьян. Просто потолок опять спорит со мной по-русски.",
        "У меня плохие новости: гусь выиграл суд и теперь владеет кухней.",
        "Внимание! Священник сбежал, баян остался, свадьбу отменяем.",
        "Мне позвонил сатана и попросил вернуть его чёртов пылесос.",
        "КТО-НИБУДЬ ВИДЕЛ МОЙ ПАСПОРТ? ЕГО УКРАЛА ЖЕНЩИНА В КОСТЮМЕ КАРТОШКИ.",
        "Это полный пиздец. Даже банкомат вызвал психолога.",
    ],
    "polish": [
        "KTO DO CHOLERY ZAMKNĄŁ KSIĘDZA W LODÓWCE?!",
        "Kurwa mać, dlaczego mój odkurzacz ma adwokata?",
        "Nie jestem pijany. Po prostu ściana zadaje bardzo osobiste pytania.",
        "W piwnicy siedzi księgowy bez spodni i twierdzi, że jest moim ojcem.",
        "Kto ukradł moje zęby i zostawił paragon za kebaba?",
        "JA PIERDOLĘ. GOŁĄB WYGRAŁ WYBORY I CHCE PODATKÓW.",
        "Mój sąsiad właśnie ochrzcił mikrofalówkę piwem. Co za pojebany wtorek.",
        "Przepraszam, czy ten koń ma pozwolenie na prowadzenie pogrzebu?",
        "NIE OTWIERAJ WALIZKI. TO NIE JEST SER, TO JEST PROBLEM PRAWNY.",
        "Moja była napisała do mnie z numeru telefonu opętanego tostera.",
        "Dlaczego diabeł zostawił mi fakturę za parking?",
        "Dziś rano znalazłem śledzia w bucie i oficjalne pismo z Watykanu.",
    ],
    "ukrainian": [
        "Хто, бляха, залишив труну в моєму холодильнику?",
        "Я прокинувся, а на кухні бухгалтер у весільній сукні.",
        "Це не жарт. Мій пилосос вимагає адвоката.",
        "ТА ЯКОГО БІСА ГУСАК КЕРУЄ ЦІЄЮ КОМПАНІЄЮ?!",
        "Мені подзвонив диявол і попросив повернути йому чайник.",
        "Священник утік, баян залишився. Весілля під загрозою.",
        "Я більше не довіряю цій шафі. Вона знає моє друге ім'я.",
        "Хто продав мої черевики чоловікові на ім'я Капуста?",
        "ЦЕ ПОВНА ДУПА. НАВІТЬ ПРИВИД ВИКЛИКАВ ПОЛІЦІЮ.",
        "У підвалі сидить гусак у краватці й вимагає орендну плату.",
        "Мій сусід намагається освятити пральну машину о третій ночі.",
        "Поясніть, чому в моїй поштовій скриньці лежить чужий зуб і чек за борщ.",
    ],
    "czech": [
        "DO PRDELE, KDO MI UKRADL RAKVIČKU A NECHAL TADY ÚČTENKU?",
        "V lednici sedí účetní bez kalhot a tvrdí, že je můj nový táta.",
        "To si děláš prdel? Ten holub má vlastní právnickou firmu.",
        "Ráno mi volal ďábel. Prý mu dlužím vysavač.",
        "PROČ MÁ TEN KNĚZ NA HLAVĚ MIKROVLNKU?!",
        "Včera jsem se pohádal s bankomatem. Prohrál jsem soud.",
        "Můj soused pokřtil topinkovač a teď chce rozvod.",
        "Nikdo neotvírejte kufr. Je tam jen sýr a pár nezodpovězených otázek.",
        "Já nejsem blázen. Jen moje lednice platí nájem pozdě.",
        "KDE JE TEN ZASRANEJ AKORDEON? POHŘEB ZAČÍNÁ ZA PĚT MINUT!",
        "V garáži stojí muž v obleku a prodává zuby na splátky.",
        "Tenhle týden mě vyhodili z kostela i z automatu na kávu.",
    ],
    "serbian": [
        "KOJI KURAC JE OSTAVIO MRTVAČKI SANDUK U KUHINJI?!",
        "Brate, frižider mi traži alimentaciju. Nisam spreman za ovo.",
        "Nisam pijan, majke mi. Samo mi usisivač priča o razvodu.",
        "U podrumu sedi računovođa bez pantalona i pita gde je pop.",
        "JEBOTE, GOLUB MI JE UZEO PASOŠ I OTIŠAO NA SVADBU.",
        "Ko je pozvao harmonikaša na egzorcizam? Hoću ime i prezime.",
        "Đavo me zvao u tri ujutru. Kaže da mu dugujem deset evra.",
        "NE OTVARAJ KOFER. UNUTRA SU SAMO ZUBI I LOŠE ODLUKE.",
        "Moj komšija je venčao mikrotalasnu i sad traži kumove.",
        "Jutros sam našao bure u liftu. Na buretu piše 'NE PITAJ'.",
        "Ne znam ko je vlasnik te koze, ali advokat je već stigao.",
        "Ako me traže, reci da sam na sahrani svog dostojanstva.",
    ],
}

CONTEXT = {
    "food": [
        "Don't eat that shit. I saw a priest try to exorcise the mayonnaise an hour ago.",
        "I've eaten worse. The health inspector still sends me threatening Christmas cards.",
        "You say food. I hear 'evidence from an unsolved motel incident.'",
    ],
    "love": [
        "Romance is dead and somebody has been charging its credit card at the liquor store.",
        "I once fell in love with a parking meter. She was emotionally unavailable and took all my change.",
        "Love is beautiful until the ghost asks for half the security deposit.",
    ],
    "money": [
        "My financial advisor is a man named Horse Divorce and frankly I'm thriving.",
        "I'm two missed payments away from selling cursed dental equipment behind a Walmart.",
        "I have money. Just not in any currency recognized by this fucking dimension.",
    ],
    "sleep": [
        "Sleep? No thanks. The man in the radiator has a midnight podcast.",
        "I tried sleeping. Woke up owing a goat $600 and a formal apology.",
        "The last time I slept, my furniture elected a new government.",
    ],
    "work": [
        "Tell your boss I'm legally dead between lunch and 3 PM.",
        "Corporate asked for a team-building exercise. I brought a cursed Ouija board and two divorce lawyers.",
        "The only thing I bring to the workplace is bad news and a suspicious smell of gasoline.",
    ],
    "games": [
        "I can't queue right now. My controller is at confession and the priest is losing.",
        "This game has the matchmaking of a haunted unemployment office.",
        "I would help, but I just lost a 1v1 to a man operating his keyboard with a sausage.",
    ],
}
CONTEXT_PATTERN = {
    "food": r"\b(food|eat|eating|hungry|dinner|pizza|chicken|lunch|breakfast)\b",
    "love": r"\b(love|dating|girlfriend|boyfriend|wife|husband|marry|relationship|crush|ex)\b",
    "money": r"\b(money|broke|cash|paid|pay|rent|bank|debt|dollars|taxes)\b",
    "sleep": r"\b(sleep|tired|bed|dream|awake|insomnia|nap)\b",
    "work": r"\b(work|boss|job|shift|fired|coworker|office)\b",
    "games": r"\b(game|gaming|discord|server|ranked|match|steam|controller|fps)\b",
}

# Mix-and-match is deliberately infrequent so canned Franken-sentences don't
# displace the individually authored, properly strange one-liners.
SUBJECTS = [
    "a disgraced priest", "an extremely horny accountant", "a man named Pork Mortgage",
    "a disbarred magician", "a forklift in lingerie", "a ghost with outstanding parking fines",
    "a naked guy with a briefcase", "a suspiciously muscular funeral director",
    "the local sewer inspector", "a prostitute-shaped lawn ornament",
    "a dentist on the run", "a retired exorcist with six fake passports",
]
ACCUSATIONS = [
    "is currently living in my walls and charging me rent",
    "has demanded a paternity test from the moon",
    "is under investigation for marrying the photocopier",
    "has been selling illegal teeth outside the bowling alley",
    "has requested a private exorcism of the group chat",
    "just sent me an invoice for emotional damage and six sausages",
    "was caught holding hands with a haunted parking ticket",
    "has announced a suspiciously sensual funeral at dawn",
]

LANGUAGE_ALIASES = {
    "ru": "russian", "pl": "polish", "uk": "ukrainian", "cs": "czech", "sr": "serbian",
    "random": "random", "russian": "russian", "polish": "polish",
    "ukrainian": "ukrainian", "czech": "czech", "serbian": "serbian",
}


def generate_response(
    message: str = "", mode: str = "feral", followup: bool = False,
    slavic_chance: int = 25, slavic_language: str = "random",
) -> str:
    """Return a wild, non-pinging line without connecting to outside services.

    Slavic chance applies separately to each generated message, including
    direct bot mentions, questions and short follow-up turns.
    """
    cleaned = re.sub(r"<@!?\d+>", "", message or "").strip().lower()
    words = re.findall(r"[a-z']+", cleaned)
    first = words[0] if words else ""
    mode = mode if mode in ("tame", "wild", "feral") else "feral"
    slavic_chance = max(0, min(100, int(slavic_chance)))

    if mode != "tame" and random.random() * 100 < slavic_chance:
        language = LANGUAGE_ALIASES.get(slavic_language.lower(), "random")
        if language == "random":
            language = random.choice(tuple(SLAVIC))
        return random.choice(SLAVIC[language])

    if followup:
        if first in {"yes", "yeah", "yep", "sure", "absolutely"} and random.random() < 0.35:
            return random.choice(AFFIRMATION)
        if first in {"no", "nope", "nah", "never"} and random.random() < 0.35:
            return random.choice(DENIAL)
        return random.choice(FOLLOWUPS)

    if first in {"hey", "hello", "hi", "sup", "howdy", "yo"} and random.random() < 0.60:
        return random.choice(GREETING)

    if "?" in cleaned and random.random() < 0.72:
        question = {"why": WHY, "how": HOW, "who": WHO, "whose": WHO,
                    "what": WHAT, "which": WHAT, "when": WHEN}.get(first, YES_NO)
        return random.choice(question)

    if first in {"yes", "yeah", "yep", "sure", "absolutely"} and random.random() < 0.35:
        return random.choice(AFFIRMATION)
    if first in {"no", "nope", "nah", "never"} and random.random() < 0.35:
        return random.choice(DENIAL)

    if random.random() < 0.24:
        return random.choice(QUESTIONS)

    if random.random() < 0.18:
        categories = [name for name, pattern in CONTEXT_PATTERN.items()
                      if re.search(pattern, cleaned)]
        if categories:
            return random.choice(CONTEXT[random.choice(categories)])

    if mode == "tame":
        pool = TAME
    elif mode == "wild":
        pool = WILD + TAME[:8]
    else:
        pool = FERAL + WILD

    if mode == "feral" and random.random() < 0.09:
        return f"I have breaking fucking news: {random.choice(SUBJECTS)} {random.choice(ACCUSATIONS)}."

    return random.choice(pool)
