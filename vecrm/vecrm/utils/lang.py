"""S145b: per-employee language for VECRM mails and pushes (English, Hindi, Gujarati).

Rulings (Ajay, 25 Sep 2026):
- The language is saved on the employee (VECRM Employee.preferred_language).
  The portal language switch writes it; mails and pushes follow it.
- Default English. Hindi and Gujarati use the words the team says, written in
  their own script (वाउचर / વાઉચર, एडवांस / એડવાન્સ); acronyms stay Latin
  (OT, UPI, PIN, OTP, BOQ); digits 0-9; dates and amounts keep the existing
  formatters (English month abbreviations, "Rs 1,234.00").
- Messages to a person follow that person's language. Messages to a group
  mailbox or the Accounts / audit lists stay English.

Templates use str.format placeholders. Callers escape any value that goes into
HTML before passing it; templates themselves carry no HTML.
"""

from __future__ import annotations

import frappe

LANGS = ("en", "hi", "gu")

# key: (English, Hindi, Gujarati)
MESSAGES: dict[str, tuple[str, str, str]] = {
    # ── common ────────────────────────────────────────────────────────────
    "hi_name": ("Hi {name},", "नमस्ते {name},", "નમસ્તે {name},"),
    "reason": ("Reason: {reason}", "कारण: {reason}", "કારણ: {reason}"),
    "col.name": ("Name", "नाम", "નામ"),
    "col.role": ("Role", "रोल", "રોલ"),
    "col.status": ("Status", "स्टेटस", "સ્ટેટસ"),
    "col.voucher": ("Voucher", "वाउचर", "વાઉચર"),
    "col.type": ("Type", "प्रकार", "પ્રકાર"),
    "col.approved": ("Approved", "मंज़ूर रकम", "મંજૂર રકમ"),
    "col.advance_deducted": ("Advance deducted", "एडवांस कटा", "એડવાન્સ કપાયું"),
    "col.paid": ("Paid", "पेमेंट", "પેમેન્ટ"),
    "col.covered": ("Covered by advance", "एडवांस से पूरा हुआ", "એડવાન્સથી પૂરું થયું"),
    "col.advance": ("Advance", "एडवांस", "એડવાન્સ"),
    "col.site": ("Site", "साइट", "સાઇટ"),
    "kind.Petrol": ("Petrol", "पेट्रोल", "પેટ્રોલ"),
    "kind.Expense": ("Expense", "एक्सपेंस", "એક્સપેન્સ"),

    # ── voucher approve / reject / paid pushes ────────────────────────────
    "push.voucher.Approved.title": ("Voucher approved", "वाउचर मंज़ूर", "વાઉચર મંજૂર"),
    "push.voucher.Approved.body": ("Your voucher {name} was approved",
                                   "आपका वाउचर {name} मंज़ूर हो गया",
                                   "તમારું વાઉચર {name} મંજૂર થઈ ગયું"),
    "push.voucher.Rejected.title": ("Voucher rejected", "वाउचर नामंज़ूर", "વાઉચર નામંજૂર"),
    "push.voucher.Rejected.body": ("Your voucher {name} was rejected",
                                   "आपका वाउचर {name} नामंज़ूर हो गया",
                                   "તમારું વાઉચર {name} નામંજૂર થયું"),
    "push.voucher.Paid.title": ("Voucher paid", "वाउचर का पेमेंट हुआ", "વાઉચરનું પેમેન્ટ થયું"),
    "push.voucher.Paid.body": ("Your voucher {name} was paid",
                               "आपके वाउचर {name} का पेमेंट हो गया",
                               "તમારા વાઉચર {name} નું પેમેન્ટ થઈ ગયું"),

    # ── voucher submitted (to approvers) ──────────────────────────────────
    "push.vsub.title": ("New voucher submitted", "नया वाउचर जमा हुआ", "નવું વાઉચર જમા થયું"),
    "push.vsub.travel": ("New petrol voucher submitted by {name}",
                         "{name} ने नया पेट्रोल वाउचर जमा किया",
                         "{name} એ નવું પેટ્રોલ વાઉચર જમા કર્યું"),
    "push.vsub.expense": ("New expense voucher submitted by {name}",
                          "{name} ने नया एक्सपेंस वाउचर जमा किया",
                          "{name} એ નવું એક્સપેન્સ વાઉચર જમા કર્યું"),

    # ── voucher period push (all users) ───────────────────────────────────
    "push.period.title": ("Vouchers due {deadline}",
                          "वाउचर जमा करने की आखिरी तारीख {deadline}",
                          "વાઉચર જમા કરવાની છેલ્લી તારીખ {deadline}"),
    "push.period.h1": ("first half of {mon} (1st to 15th)",
                       "{mon} का पहला हिस्सा (1 से 15 तारीख)",
                       "{mon} નો પહેલો ભાગ (1 થી 15 તારીખ)"),
    "push.period.h2": ("second half of {mon} (16th to {last})",
                       "{mon} का दूसरा हिस्सा (16 से {last} तारीख)",
                       "{mon} નો બીજો ભાગ (16 થી {last} તારીખ)"),
    "push.period.body": ("Submit your {period} petrol, travel and expense vouchers by {deadline}.",
                         "{period} के अपने पेट्रोल, ट्रैवल और एक्सपेंस वाउचर {deadline} तक जमा करें।",
                         "{period} ના તમારા પેટ્રોલ, ટ્રાવેલ અને એક્સપેન્સ વાઉચર {deadline} સુધીમાં જમા કરો."),
    "push.period.tonight": (" The window opens tonight at 9pm. File tonight to be recorded as on time.",
                            " विंडो आज रात 9 बजे खुलेगी। समय पर गिने जाने के लिए आज रात ही जमा करें।",
                            " વિન્ડો આજે રાત્રે 9 વાગ્યે ખુલશે. સમયસર ગણાય તે માટે આજે રાત્રે જ જમા કરો."),
    "push.period.tomorrow": (" The window opens tomorrow at 9pm.",
                             " विंडो कल रात 9 बजे खुलेगी।",
                             " વિન્ડો આવતીકાલે રાત્રે 9 વાગ્યે ખુલશે."),

    # ── approver reminders ────────────────────────────────────────────────
    "push.appr.title": ("Voucher action required", "वाउचर पर कार्रवाई करें", "વાઉચર પર કાર્યવાહી કરો"),
    "push.appr.h1": ("Please approve pending vouchers for the 1st-15th period. Submission closed on the 20th.",
                     "1 से 15 तारीख के बाकी वाउचर मंज़ूर करें। जमा करने की आखिरी तारीख 20 थी।",
                     "1 થી 15 તારીખના બાકી વાઉચર મંજૂર કરો. જમા કરવાની છેલ્લી તારીખ 20 હતી."),
    "push.appr.h2": ("Please approve pending vouchers for the previous month's 16th-to-end period. "
                     "Submission closed on the 5th.",
                     "पिछले महीने की 16 से आखिरी तारीख तक के बाकी वाउचर मंज़ूर करें। जमा करने की आखिरी तारीख 5 थी।",
                     "ગયા મહિનાની 16 થી છેલ્લી તારીખ સુધીના બાકી વાઉચર મંજૂર કરો. જમા કરવાની છેલ્લી તારીખ 5 હતી."),
    "push.appr.pay_h1": ("Voucher payments for the 1st-15th period open today. Window is the 20th to the 25th.",
                         "1 से 15 तारीख के वाउचर पेमेंट आज से शुरू। पेमेंट 20 से 25 तारीख के बीच होगा।",
                         "1 થી 15 તારીખના વાઉચર પેમેન્ટ આજથી શરૂ. પેમેન્ટ 20 થી 25 તારીખ વચ્ચે થશે."),
    "push.appr.pay_h2": ("Voucher payments for the previous month's 16th-to-end period open today. "
                         "Window is the 8th to the 12th.",
                         "पिछले महीने की 16 से आखिरी तारीख तक के वाउचर पेमेंट आज से शुरू। पेमेंट 8 से 12 तारीख के बीच होगा।",
                         "ગયા મહિનાની 16 થી છેલ્લી તારીખ સુધીના વાઉચર પેમેન્ટ આજથી શરૂ. પેમેન્ટ 8 થી 12 તારીખ વચ્ચે થશે."),

    # ── auto-submit / relock ──────────────────────────────────────────────
    "push.auto_none.title": ("No voucher filed", "कोई वाउचर नहीं भरा", "કોઈ વાઉચર ભર્યું નથી"),
    "push.auto_none.body": ("No petrol voucher was filed for {period}. Nothing was submitted.",
                            "{period} के लिए कोई पेट्रोल वाउचर नहीं भरा गया। कुछ भी जमा नहीं हुआ।",
                            "{period} માટે કોઈ પેટ્રોલ વાઉચર ભરાયું નથી. કશું જમા થયું નથી."),
    "push.auto_done.title": ("Voucher auto-submitted", "वाउचर अपने-आप जमा हुआ", "વાઉચર આપમેળે જમા થયું"),
    "push.auto_done.body": ("Your {period} petrol voucher {name} was auto-submitted for approval.",
                            "आपका {period} का पेट्रोल वाउचर {name} मंज़ूरी के लिए अपने-आप जमा हो गया।",
                            "તમારું {period} નું પેટ્રોલ વાઉચર {name} મંજૂરી માટે આપમેળે જમા થઈ ગયું."),
    "push.relock.title": ("Edit window closed", "एडिट का समय खत्म", "એડિટનો સમય પૂરો"),
    "push.relock.body": ("The 24-hour edit window for {name} closed; it's back in the approval queue.",
                         "{name} को एडिट करने के 24 घंटे पूरे हो गए; यह फिर से मंज़ूरी के लिए लाइन में है।",
                         "{name} ને એડિટ કરવાના 24 કલાક પૂરા થયા; તે ફરીથી મંજૂરી માટે લાઇનમાં છે."),

    # ── leads (sales) ─────────────────────────────────────────────────────
    "push.lead_day.title": ("Log today's meetings", "आज की मीटिंग दर्ज करें", "આજની મીટિંગ નોંધો"),
    "push.lead_day.body": ("Don't forget to add any leads or meeting notes in Anusuya Workspace.",
                           "Anusuya Workspace में लीड या मीटिंग नोट्स जोड़ना न भूलें।",
                           "Anusuya Workspace માં લીડ અથવા મીટિંગ નોટ્સ ઉમેરવાનું ભૂલશો નહીં."),
    "push.lead_assigned.title": ("New lead assigned", "नई लीड मिली", "નવી લીડ સોંપાઈ"),
    "push.lead_assigned.body": ("New lead: {company} assigned to you",
                                "नई लीड: {company} आपको दी गई है",
                                "નવી લીડ: {company} તમને સોંપવામાં આવી છે"),
    "push.lead_status.title": ("Lead status: {company}", "लीड स्टेटस: {company}", "લીડ સ્ટેટસ: {company}"),
    "push.lead_status.body": ("{company}: {old} → {new}", "{company}: {old} → {new}", "{company}: {old} → {new}"),
    "push.lead_closed.title": ("Lead {status}: {company}", "लीड {status}: {company}", "લીડ {status}: {company}"),
    "push.lead_closed.body": ("Lead marked as {status} by {owner}",
                              "{owner} ने लीड को {status} किया",
                              "{owner} એ લીડને {status} કરી"),
    "push.lead_converted.title": ("Lead converted", "लीड कन्वर्ट हुई", "લીડ કન્વર્ટ થઈ"),
    "push.lead_converted.body": ("Lead converted: {company} → new inquiry {inquiry}",
                                 "लीड कन्वर्ट हुई: {company} → नई इन्क्वायरी {inquiry}",
                                 "લીડ કન્વર્ટ થઈ: {company} → નવી ઇન્ક્વાયરી {inquiry}"),
    "push.followup_today.title": ("Follow-up due today", "आज फॉलो-अप करना है", "આજે ફોલો-અપ કરવાનું છે"),
    "push.followup_today.body": ("Follow-up due today for {company}",
                                 "{company} का फॉलो-अप आज करना है",
                                 "{company} નું ફોલો-અપ આજે કરવાનું છે"),
    "push.followup_tomorrow.title": ("Follow-up due tomorrow", "कल फॉलो-अप करना है", "આવતીકાલે ફોલો-અપ કરવાનું છે"),
    "push.followup_tomorrow.body": ("Upcoming follow-up tomorrow for {company}",
                                    "{company} का फॉलो-अप कल करना है",
                                    "{company} નું ફોલો-અપ આવતીકાલે કરવાનું છે"),
    "push.stale.title": ("Inquiry needs a follow-up", "इन्क्वायरी पर फॉलो-अप करें", "ઇન્ક્વાયરી પર ફોલો-અપ કરો"),
    "push.stale.body": ("Your inquiry for {company} hasn't been updated recently. Give them a call?",
                        "{company} की आपकी इन्क्वायरी हाल में अपडेट नहीं हुई है। एक कॉल कर लें?",
                        "{company} ની તમારી ઇન્ક્વાયરી હમણાં અપડેટ થઈ નથી. એક કોલ કરી લો?"),
    "push.intent.title": ("Set call intent", "कॉल का इंटेंट चुनें", "કોલનો ઇન્ટેન્ટ પસંદ કરો"),
    "push.intent.body": ("Update the intent for your call to {number}",
                         "{number} पर की गई कॉल का इंटेंट अपडेट करें",
                         "{number} પર કરેલા કોલનો ઇન્ટેન્ટ અપડેટ કરો"),
    "push.intent.a_lead": ("a lead", "एक लीड", "એક લીડ"),

    # ── petrol voucher due (voucher_due) ──────────────────────────────────
    "vd.rem.subject": ("Petrol voucher due by {deadline}: {label}",
                       "पेट्रोल वाउचर {deadline} तक जमा करें: {label}",
                       "પેટ્રોલ વાઉચર {deadline} સુધીમાં જમા કરો: {label}"),
    "vd.rem.pre": ("Petrol voucher due", "पेट्रोल वाउचर बाकी", "પેટ્રોલ વાઉચર બાકી"),
    "vd.rem.draft": ("Your petrol voucher for {label} is still a draft with {n} line(s). "
                     "A draft is not filed until you submit it.",
                     "{label} का आपका पेट्रोल वाउचर अभी ड्राफ्ट है, उसमें {n} लाइन हैं। "
                     "जमा करने तक ड्राफ्ट को भरा हुआ नहीं माना जाता।",
                     "{label} નું તમારું પેટ્રોલ વાઉચર હજી ડ્રાફ્ટ છે, તેમાં {n} લાઇન છે. "
                     "જમા કરો ત્યાં સુધી ડ્રાફ્ટ ભરેલું ગણાતું નથી."),
    "vd.rem.none": ("Your petrol voucher for {label} has not been filed yet.",
                    "{label} का आपका पेट्रोल वाउचर अभी तक नहीं भरा गया है।",
                    "{label} નું તમારું પેટ્રોલ વાઉચર હજી ભરાયું નથી."),
    "vd.rem.close": ("The window closes on {date} at 11:59 pm.",
                     "विंडो {date} को रात 11:59 बजे बंद होगी।",
                     "વિન્ડો {date} ના રોજ રાત્રે 11:59 વાગ્યે બંધ થશે."),
    "vd.rem.ontime": ("The submission window opens tonight at 9 pm. File tonight to be recorded as on time.",
                      "जमा करने की विंडो आज रात 9 बजे खुलेगी। समय पर गिने जाने के लिए आज रात जमा करें।",
                      "જમા કરવાની વિન્ડો આજે રાત્રે 9 વાગ્યે ખુલશે. સમયસર ગણાય તે માટે આજે રાત્રે જમા કરો."),
    "vd.rem.late": ("Filing now is recorded as Late.",
                    "अभी जमा करने पर यह लेट गिना जाएगा।",
                    "હવે જમા કરશો તો લેટ ગણાશે."),
    "vd.rem.open": ("Open it here: {link}", "यहाँ खोलें: {link}", "અહીં ખોલો: {link}"),
    "vd.link.petrol": ("Petrol vouchers", "पेट्रोल वाउचर", "પેટ્રોલ વાઉચર"),
    "vd.rem.noclaim": ("If you had no petrol spend this period, open the Anusuya app and tap "
                       "\"No petrol claim this period\" so you are not reminded again.",
                       "अगर इस बार पेट्रोल का कोई खर्च नहीं हुआ, तो Anusuya ऐप खोलें और "
                       "\"पेट्रोल का कोई क्लेम नहीं\" वाला बटन दबाएँ, ताकि दोबारा याद न दिलाया जाए।",
                       "જો આ વખતે પેટ્રોલનો કોઈ ખર્ચ ન થયો હોય, તો Anusuya એપ ખોલો અને "
                       "\"પેટ્રોલનો કોઈ ક્લેમ નથી\" વાળું બટન દબાવો, જેથી ફરી યાદ ન કરાવાય."),
    "vd.hod.subject": ("Petrol vouchers not filed: {label} ({n})",
                       "पेट्रोल वाउचर नहीं भरे गए: {label} ({n})",
                       "પેટ્રોલ વાઉચર ભરાયા નથી: {label} ({n})"),
    "vd.hod.pre": ("Petrol vouchers not filed", "पेट्रोल वाउचर नहीं भरे गए", "પેટ્રોલ વાઉચર ભરાયા નથી"),
    "vd.hod.body": ("These people in your team have not filed their petrol voucher for {label}. "
                    "The window closes on {date} at 11:59 pm.",
                    "आपकी टीम के इन लोगों ने {label} का पेट्रोल वाउचर नहीं भरा है। "
                    "विंडो {date} को रात 11:59 बजे बंद होगी।",
                    "તમારી ટીમના આ લોકોએ {label} નું પેટ્રોલ વાઉચર ભર્યું નથી. "
                    "વિન્ડો {date} ના રોજ રાત્રે 11:59 વાગ્યે બંધ થશે."),
    "vd.hod.st_draft": ("Draft, {n} line(s), not submitted",
                        "ड्राफ्ट, {n} लाइन, जमा नहीं",
                        "ડ્રાફ્ટ, {n} લાઇન, જમા નથી"),
    "vd.hod.st_none": ("Not filed", "नहीं भरा", "ભર્યું નથી"),
    "vd.link.overview": ("Open the voucher overview", "वाउचर ओवरव्यू खोलें", "વાઉચર ઓવરવ્યૂ ખોલો"),
    "vd.sub.subject.petrol": ("{who} submitted a petrol voucher: {name}",
                              "{who} ने पेट्रोल वाउचर जमा किया: {name}",
                              "{who} એ પેટ્રોલ વાઉચર જમા કર્યું: {name}"),
    "vd.sub.subject.expense": ("{who} submitted an expense voucher: {name}",
                               "{who} ने एक्सपेंस वाउचर जमा किया: {name}",
                               "{who} એ એક્સપેન્સ વાઉચર જમા કર્યું: {name}"),
    "vd.sub.body.petrol": ("{who} has submitted petrol voucher {name} for {amount}.",
                           "{who} ने {amount} का पेट्रोल वाउचर {name} जमा किया है।",
                           "{who} એ {amount} નું પેટ્રોલ વાઉચર {name} જમા કર્યું છે."),
    "vd.sub.body.expense": ("{who} has submitted expense voucher {name} for {amount}.",
                            "{who} ने {amount} का एक्सपेंस वाउचर {name} जमा किया है।",
                            "{who} એ {amount} નું એક્સપેન્સ વાઉચર {name} જમા કર્યું છે."),
    "vd.sub.pre": ("Voucher submitted", "वाउचर जमा हुआ", "વાઉચર જમા થયું"),
    "vd.link.review": ("Review it in the voucher overview", "वाउचर ओवरव्यू में देखें", "વાઉચર ઓવરવ્યૂમાં જુઓ"),
    "vd.paid.lead": ("{amount} has been paid to your bank account for the voucher(s) below.",
                     "नीचे दिए वाउचर के लिए {amount} आपके बैंक खाते में भेज दिए गए हैं।",
                     "નીચેના વાઉચર માટે {amount} તમારા બેંક ખાતામાં મોકલી દેવાયા છે."),
    "vd.paid.settled": ("The voucher(s) below were fully covered by the advance you had already "
                        "received, so no bank payment was made for them.",
                        "नीचे दिए वाउचर आपको पहले मिले एडवांस से पूरे हो गए, इसलिए उनके लिए "
                        "बैंक में कोई पेमेंट नहीं हुआ।",
                        "નીચેના વાઉચર તમને પહેલાં મળેલા એડવાન્સથી પૂરા થઈ ગયા, એટલે તેમના માટે "
                        "બેંકમાં કોઈ પેમેન્ટ થયું નથી."),
    "vd.paid.note": ("Advance deducted is the advance you had already received against that "
                     "voucher, including any balance carried forward from an earlier trip.",
                     "\"एडवांस कटा\" वह एडवांस है जो आपको उस वाउचर के लिए पहले मिल चुका था, "
                     "पिछली ट्रिप का बचा हुआ बैलेंस भी इसमें शामिल है।",
                     "\"એડવાન્સ કપાયું\" એ એડવાન્સ છે જે તમને તે વાઉચર માટે પહેલાં મળી ચૂક્યું હતું, "
                     "અગાઉની ટ્રિપનું બાકી બેલેન્સ પણ તેમાં સામેલ છે."),
    "vd.link.vouchers": ("See your vouchers", "अपने वाउचर देखें", "તમારા વાઉચર જુઓ"),
    "vd.paid.subject": ("Voucher payment: {amount} paid",
                        "वाउचर पेमेंट: {amount} भेजे गए",
                        "વાઉચર પેમેન્ટ: {amount} મોકલાયા"),
    "vd.paid.subject_settled": ("Voucher settled against your advance: {names}",
                                "वाउचर आपके एडवांस से पूरा हुआ: {names}",
                                "વાઉચર તમારા એડવાન્સથી પૂરું થયું: {names}"),
    "vd.paid.pre": ("Voucher payment", "वाउचर पेमेंट", "વાઉચર પેમેન્ટ"),

    # ── expense advances (advance.py) ─────────────────────────────────────
    "adv.f.advance": ("Advance", "एडवांस", "એડવાન્સ"),
    "adv.f.employee": ("Employee", "कर्मचारी", "કર્મચારી"),
    "adv.f.requested": ("Amount requested", "माँगी गई रकम", "માગેલી રકમ"),
    "adv.f.paid": ("Amount paid", "दी गई रकम", "આપેલી રકમ"),
    "adv.f.ref": ("UPI / payment ref", "UPI / पेमेंट रेफरेंस", "UPI / પેમેન્ટ રેફરન્સ"),
    "adv.f.site": ("Site", "साइट", "સાઇટ"),
    "adv.f.location": ("Location", "जगह", "જગ્યા"),
    "adv.f.travel": ("Travel", "यात्रा", "મુસાફરી"),
    "adv.f.travel_val": ("{start} to {end}", "{start} से {end}", "{start} થી {end}"),
    "adv.f.purpose": ("Purpose", "काम", "કામ"),
    "adv.f.topup_of": ("Top-up of", "इसका टॉप-अप", "આનું ટોપ-અપ"),
    "adv.link.open": ("Open the advance", "एडवांस खोलें", "એડવાન્સ ખોલો"),
    "adv.link.decide": ("Open to approve or reject", "मंज़ूर या नामंज़ूर करने के लिए खोलें",
                        "મંજૂર અથવા નામંજૂર કરવા ખોલો"),
    "adv.link.pay": ("Open to mark paid", "पेमेंट दर्ज करने के लिए खोलें", "પેમેન્ટ નોંધવા ખોલો"),
    "adv.link.voucher": ("Open the voucher", "वाउचर खोलें", "વાઉચર ખોલો"),
    "adv.your_head": ("Your head", "आपके हेड", "તમારા હેડ"),
    "adv.req.subject": ("Advance request received: {amount}, {site}",
                        "एडवांस की माँग मिली: {amount}, {site}",
                        "એડવાન્સની માગણી મળી: {amount}, {site}"),
    "adv.req.body": ("Your advance request {name} for {amount} is with {who} for approval.",
                     "{amount} की आपकी एडवांस माँग {name} मंज़ूरी के लिए {who} के पास है।",
                     "{amount} ની તમારી એડવાન્સ માગણી {name} મંજૂરી માટે {who} પાસે છે."),
    "adv.req.pre": ("Advance request received", "एडवांस की माँग मिली", "એડવાન્સની માગણી મળી"),
    "adv.req.push_t": ("Advance requested", "एडवांस माँगा गया", "એડવાન્સ માગ્યું"),
    "adv.req.push_b": ("{amount} for {site} sent for approval",
                       "{site} के लिए {amount} मंज़ूरी के लिए भेजा गया",
                       "{site} માટે {amount} મંજૂરી માટે મોકલાયું"),
    "adv.ask.subject": ("Advance to approve: {emp}, {amount}, {site}",
                        "मंज़ूर करने के लिए एडवांस: {emp}, {amount}, {site}",
                        "મંજૂર કરવા માટે એડવાન્સ: {emp}, {amount}, {site}"),
    "adv.ask.body": ("{emp} has requested an expense advance. Please approve or reject it.",
                     "{emp} ने एक्सपेंस एडवांस माँगा है। कृपया मंज़ूर या नामंज़ूर करें।",
                     "{emp} એ એક્સપેન્સ એડવાન્સ માગ્યું છે. કૃપા કરીને મંજૂર અથવા નામંજૂર કરો."),
    "adv.ask.pre": ("Advance to approve", "मंज़ूर करने के लिए एडवांस", "મંજૂર કરવા માટે એડવાન્સ"),
    "adv.ask.push_b": ("{emp}: {amount} for {site}", "{emp}: {site} के लिए {amount}", "{emp}: {site} માટે {amount}"),
    "adv.obo.subject": ("Advance raised for you: {amount}, {site}",
                        "आपके लिए एडवांस माँगा गया: {amount}, {site}",
                        "તમારા માટે એડવાન્સ માગવામાં આવ્યું: {amount}, {site}"),
    "adv.obo.body": ("{who} raised advance {name} for you and it counts as approved. "
                     "It now goes to Accounts for payment.",
                     "{who} ने आपके लिए एडवांस {name} माँगा है और इसे मंज़ूर माना गया है। "
                     "अब यह पेमेंट के लिए अकाउंट्स के पास जाएगा।",
                     "{who} એ તમારા માટે એડવાન્સ {name} માગ્યું છે અને તે મંજૂર ગણાય છે. "
                     "હવે તે પેમેન્ટ માટે અકાઉન્ટ્સ પાસે જશે."),
    "adv.obo.pre": ("Advance raised for you", "आपके लिए एडवांस माँगा गया", "તમારા માટે એડવાન્સ માગવામાં આવ્યું"),
    "adv.obo.push_b": ("{amount} for {site}, approved", "{site} के लिए {amount}, मंज़ूर", "{site} માટે {amount}, મંજૂર"),
    "adv.ok.subject": ("Advance approved: {amount}, {site}",
                       "एडवांस मंज़ूर: {amount}, {site}",
                       "એડવાન્સ મંજૂર: {amount}, {site}"),
    "adv.ok.body": ("{who} approved your advance {name}. It now goes to Accounts for payment.",
                    "{who} ने आपका एडवांस {name} मंज़ूर कर दिया। अब यह पेमेंट के लिए अकाउंट्स के पास जाएगा।",
                    "{who} એ તમારું એડવાન્સ {name} મંજૂર કર્યું. હવે તે પેમેન્ટ માટે અકાઉન્ટ્સ પાસે જશે."),
    "adv.ok.pre": ("Advance approved", "एडवांस मंज़ूर", "એડવાન્સ મંજૂર"),
    "adv.ok.push_b": ("{amount} for {site} approved, awaiting payment",
                      "{site} के लिए {amount} मंज़ूर, पेमेंट बाकी",
                      "{site} માટે {amount} મંજૂર, પેમેન્ટ બાકી"),
    "adv.no.subject": ("Advance not approved: {amount}, {site}",
                       "एडवांस मंज़ूर नहीं हुआ: {amount}, {site}",
                       "એડવાન્સ મંજૂર થયું નથી: {amount}, {site}"),
    "adv.no.body": ("{who} did not approve your advance {name}.",
                    "{who} ने आपका एडवांस {name} मंज़ूर नहीं किया।",
                    "{who} એ તમારું એડવાન્સ {name} મંજૂર કર્યું નથી."),
    "adv.no.pre": ("Advance not approved", "एडवांस मंज़ूर नहीं हुआ", "એડવાન્સ મંજૂર થયું નથી"),
    "adv.no.push_b": ("{amount} for {site}: {reason}", "{site} के लिए {amount}: {reason}", "{site} માટે {amount}: {reason}"),
    "adv.paid.subject": ("Advance paid: {amount}, {site}",
                         "एडवांस का पेमेंट हुआ: {amount}, {site}",
                         "એડવાન્સનું પેમેન્ટ થયું: {amount}, {site}"),
    "adv.paid.body": ("Your advance {name} has been paid: {amount}.",
                      "आपके एडवांस {name} का पेमेंट हो गया: {amount}।",
                      "તમારા એડવાન્સ {name} નું પેમેન્ટ થઈ ગયું: {amount}."),
    "adv.paid.voucher": ("Your expense voucher {voucher} is ready with this advance on it. "
                         "Add your expense lines and submit it after the trip: {link}",
                         "आपका एक्सपेंस वाउचर {voucher} इस एडवांस के साथ तैयार है। "
                         "ट्रिप के बाद अपने खर्च की लाइनें जोड़कर उसे जमा करें: {link}",
                         "તમારું એક્સપેન્સ વાઉચર {voucher} આ એડવાન્સ સાથે તૈયાર છે. "
                         "ટ્રિપ પછી તમારા ખર્ચની લાઇન ઉમેરીને તેને જમા કરો: {link}"),
    "adv.paid.pre": ("Advance paid", "एडवांस का पेमेंट हुआ", "એડવાન્સનું પેમેન્ટ થયું"),
    "adv.paid.push_b": ("{amount} paid for {site}. Voucher {voucher} is ready.",
                        "{site} के लिए {amount} का पेमेंट हुआ। वाउचर {voucher} तैयार है।",
                        "{site} માટે {amount} નું પેમેન્ટ થયું. વાઉચર {voucher} તૈયાર છે."),
    "adv.dec.subject": ("Advance payment declined: {amount}, {site}",
                        "एडवांस का पेमेंट नहीं किया गया: {amount}, {site}",
                        "એડવાન્સનું પેમેન્ટ કરવામાં આવ્યું નથી: {amount}, {site}"),
    "adv.dec.body": ("Accounts declined payment of your advance {name}.",
                     "अकाउंट्स ने आपके एडवांस {name} का पेमेंट नहीं किया।",
                     "અકાઉન્ટ્સે તમારા એડવાન્સ {name} નું પેમેન્ટ કર્યું નથી."),
    "adv.dec.pre": ("Advance payment declined", "एडवांस का पेमेंट नहीं किया गया",
                    "એડવાન્સનું પેમેન્ટ કરવામાં આવ્યું નથી"),
    "adv.dec.head_subject": ("Advance payment declined: {emp}, {amount}",
                             "एडवांस का पेमेंट नहीं किया गया: {emp}, {amount}",
                             "એડવાન્સનું પેમેન્ટ કરવામાં આવ્યું નથી: {emp}, {amount}"),
    "adv.dec.head_body": ("Accounts declined payment of advance {name}, which you approved.",
                          "आपके मंज़ूर किए एडवांस {name} का पेमेंट अकाउंट्स ने नहीं किया।",
                          "તમે મંજૂર કરેલા એડવાન્સ {name} નું પેમેન્ટ અકાઉન્ટ્સે કર્યું નથી."),
    "adv.can.subject": ("Advance request cancelled: {emp}, {amount}",
                        "एडवांस की माँग रद्द हुई: {emp}, {amount}",
                        "એડવાન્સની માગણી રદ થઈ: {emp}, {amount}"),
    "adv.can.body": ("Advance {name} was cancelled before approval.",
                     "एडवांस {name} मंज़ूरी से पहले रद्द कर दिया गया।",
                     "એડવાન્સ {name} મંજૂરી પહેલાં રદ કરવામાં આવ્યું."),
    "adv.can.pre": ("Advance cancelled", "एडवांस रद्द", "એડવાન્સ રદ"),
    "adv.can.pay_subject": ("Advance cancelled, do not pay: {emp}, {amount}",
                            "एडवांस रद्द, पेमेंट न करें: {emp}, {amount}",
                            "એડવાન્સ રદ, પેમેન્ટ ન કરો: {emp}, {amount}"),
    "adv.can.pay_body": ("Advance {name} was cancelled before payment. Do not pay it.",
                         "एडवांस {name} पेमेंट से पहले रद्द हो गया। इसका पेमेंट न करें।",
                         "એડવાન્સ {name} પેમેન્ટ પહેલાં રદ થઈ ગયું. તેનું પેમેન્ટ ન કરો."),
    "adv.can.push_b": ("Do not pay {amount} to {emp}", "{emp} को {amount} का पेमेंट न करें",
                       "{emp} ને {amount} નું પેમેન્ટ ન કરો"),
    "adv.pay.subject": ("Advance to pay: {emp}, {amount}, {site}",
                        "पेमेंट करने के लिए एडवांस: {emp}, {amount}, {site}",
                        "પેમેન્ટ કરવા માટે એડવાન્સ: {emp}, {amount}, {site}"),
    "adv.pay.body": ("Advance {name} is approved and waiting for payment. Pay it over UPI to "
                     "{emp} ({phone}), then open it and mark it paid.",
                     "एडवांस {name} मंज़ूर है और पेमेंट बाकी है। {emp} ({phone}) को UPI से पेमेंट करें, "
                     "फिर इसे खोलकर पेमेंट दर्ज करें।",
                     "એડવાન્સ {name} મંજૂર છે અને પેમેન્ટ બાકી છે. {emp} ({phone}) ને UPI થી પેમેન્ટ કરો, "
                     "પછી તેને ખોલીને પેમેન્ટ નોંધો."),
    "adv.pay.pre": ("Advance to pay", "पेमेंट करने के लिए एडवांस", "પેમેન્ટ કરવા માટે એડવાન્સ"),
    "adv.pay.push_t": ("Advance to pay", "पेमेंट करने के लिए एडवांस", "પેમેન્ટ કરવા માટે એડવાન્સ"),
    "adv.pay.none_open": ("No other advance of {emp} is still open.",
                          "{emp} का कोई दूसरा एडवांस बाकी नहीं है।",
                          "{emp} નું બીજું કોઈ એડવાન્સ બાકી નથી."),
    "adv.pay.open": ("{emp} also holds these advances, not yet settled by a paid voucher:",
                     "{emp} के पास ये एडवांस भी हैं, जो अभी किसी पेमेंट हुए वाउचर से पूरे नहीं हुए:",
                     "{emp} પાસે આ એડવાન્સ પણ છે, જે હજી કોઈ પેમેન્ટ થયેલા વાઉચરથી પૂરા થયા નથી:"),
    "adv.chase.subject": ("Submit your trip voucher: {site}, {amount} advance",
                          "अपनी ट्रिप का वाउचर जमा करें: {site}, {amount} एडवांस",
                          "તમારી ટ્રિપનું વાઉચર જમા કરો: {site}, {amount} એડવાન્સ"),
    "adv.chase.body": ("Your trip to {site} ended on {end}. You hold {amount} in advances ({advances}) "
                       "and voucher {voucher} is still a draft.",
                       "{site} की आपकी ट्रिप {end} को खत्म हुई। आपके पास {amount} एडवांस ({advances}) है "
                       "और वाउचर {voucher} अभी ड्राफ्ट है।",
                       "{site} ની તમારી ટ્રિપ {end} ના રોજ પૂરી થઈ. તમારી પાસે {amount} એડવાન્સ ({advances}) છે "
                       "અને વાઉચર {voucher} હજી ડ્રાફ્ટ છે."),
    "adv.chase.body2": ("Add your expense lines and submit it. Expenses from {end} must be submitted by {close}.",
                        "अपने खर्च की लाइनें जोड़कर उसे जमा करें। {end} के खर्च {close} तक जमा करने होंगे।",
                        "તમારા ખર્ચની લાઇન ઉમેરીને તેને જમા કરો. {end} ના ખર્ચ {close} સુધીમાં જમા કરવાના રહેશે."),
    "adv.chase.pre": ("Trip voucher pending", "ट्रिप का वाउचर बाकी", "ટ્રિપનું વાઉચર બાકી"),
    "adv.chase.push_t": ("Trip voucher pending", "ट्रिप का वाउचर बाकी", "ટ્રિપનું વાઉચર બાકી"),
    "adv.chase.push_b": ("Add lines to {voucher} and submit it", "{voucher} में लाइनें जोड़कर जमा करें",
                         "{voucher} માં લાઇન ઉમેરીને જમા કરો"),
}


def norm(lang) -> str:
    return lang if lang in LANGS else "en"


def lang_of_phone(phone) -> str:
    """preferred_language of a VECRM Employee (name = phone). English if unset."""
    if not phone:
        return "en"
    try:
        return norm(frappe.db.get_value("VECRM Employee", phone, "preferred_language"))
    except Exception:
        return "en"


def lang_of_email(email) -> str:
    if not email:
        return "en"
    try:
        return norm(frappe.db.get_value("VECRM Employee", {"vecrm_email": email}, "preferred_language"))
    except Exception:
        return "en"


class _Keep(dict):
    """Leaves an unknown {placeholder} in place instead of raising."""

    def __missing__(self, key):
        return "{" + key + "}"


def t(key: str, lang: str = "en", **kw) -> str:
    row = MESSAGES.get(key)
    if row is None:
        return key
    text = row[LANGS.index(norm(lang))] or row[0]
    try:
        return text.format_map(_Keep(kw))
    except Exception:
        return row[0].format_map(_Keep(kw))


def push_to_email(email, key_title: str, key_body: str, data: dict | None = None,
                  title_kw: dict | None = None, bell_fallback: bool = True, **body_kw) -> None:
    """One recipient: render in their language and push. With no device token,
    write the bell row instead when bell_fallback (the pre-S145b behaviour of
    each call site is kept). Best-effort."""
    if not email:
        return
    try:
        from vecrm.notifications import _log_notification, _tokens_for_user, send_push

        lang = lang_of_email(email)
        title = t(key_title, lang, **(title_kw or {}))
        body = t(key_body, lang, **body_kw)
        tokens = _tokens_for_user(email)
        if tokens:
            send_push(tokens, title, body, data or {})
        elif bell_fallback:
            _log_notification(email, title, body, data or {})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "S145b push_to_email %s" % key_title)


def push_tokens_by_language(tokens: list, render, data: dict | None = None) -> None:
    """Broadcast: group device tokens by their owner's language and send one
    multicast per language. render(lang) -> (title, body)."""
    if not tokens:
        return
    from vecrm.notifications import send_push

    rows = frappe.get_all("VECRM Device Token", filters={"fcm_token": ["in", list(tokens)]},
                          fields=["fcm_token", "user_email"], ignore_permissions=True)
    owner = {r.fcm_token: r.user_email for r in rows}
    langs = {}
    emails = sorted({e for e in owner.values() if e})
    if emails:
        for e in frappe.get_all("VECRM Employee", filters={"vecrm_email": ["in", emails]},
                                fields=["vecrm_email", "preferred_language"], ignore_permissions=True):
            langs[e.vecrm_email] = norm(e.preferred_language)
    groups = {}
    for tok in tokens:
        groups.setdefault(langs.get(owner.get(tok), "en"), []).append(tok)
    for lang, toks in groups.items():
        try:
            title, body = render(lang)
            send_push(toks, title, body, data or {})
        except Exception:
            frappe.log_error(frappe.get_traceback(), "S145b push_tokens_by_language %s" % lang)
