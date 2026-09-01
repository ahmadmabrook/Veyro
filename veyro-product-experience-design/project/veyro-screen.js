// Veyro prototype screen renderer. Mounted by Veyro Product Experience.dc.html.
// window.VeyroScreen({ screen, state }) -> the routed screen, live and interactive.
(function () {
  var R = window.React;
  var h = R.createElement;

  // ---- tokens (Design System v1, no new values) ----
  var C = {
    canvas: '#f4f2ee', surf: '#fffefb', sunk: '#faf8f4', line: 'rgba(23,23,26,.14)',
    hair: 'rgba(23,23,26,.07)', ink: '#1b4079', wash: '#e8edf6',
    t1: '#17171a', t2: '#57544d', t3: '#6b6a63', t4: '#6b6a63', dec: '#a8a29a', ctl: '#6b6a63',
    ok: '#2f5d3a', warn: '#8a5a1f', err: '#8a3b1f', info: '#3f5560', ai: '#4a3d7a', aiWash: '#edebf6',
    dBg: '#1a1917', dSurf: '#211f1c', dT1: '#f5f2ec', dT2: '#b8b3aa', dT3: '#928d84',
    dLine: 'rgba(255,255,255,.14)', dAcc: '#7ea6e8', dOk: '#6fae7f'
  };
  var mono = "'IBM Plex Mono'", sans = "'IBM Plex Sans'", ar = "'IBM Plex Sans Arabic'";
  // Which token family the shared helpers resolve against. Set by mPage.
  var DARK = false;

  var LANG = 'en';
  var AR = {"Message":"أرسل رسالة","Send":"إرسال","View":"عرض","Review":"راجع","Cancel":"إلغاء","Print":"طباعة","Save":"حفظ","Next":"التالي","Skip for now":"تخطَّ الآن","Sign in":"تسجيل الدخول","Continue":"متابعة","Resolve":"حلّ","Kill":"أوقف","Add money":"أضف رصيداً","Ate it":"أكلتها","Swap":"استبدل","Adjust":"عدّل","Search food":"ابحث عن طعام","Photo":"صورة","Barcode":"باركود","Go back":"رجوع","Keep my booking":"أبقِ الحجز","Yes, cancel it":"نعم، ألغِه","Start session":"ابدأ الحصة","Start":"ابدأ","End":"إنهاء","Pause":"إيقاف مؤقت","Log":"سجّل","Next exercise":"التمرين التالي","Add set":"أضف مجموعة","Add exercise":"أضف تمريناً","Verify and close":"وثّق وأغلق","Confirm all 22":"وثّق الـ٢٢ جميعاً","Review one at a time":"راجع واحدة تلو الأخرى","Assign it":"أسندها","Preview":"معاينة","Take payment":"استلم الدفعة","Send link":"أرسل رابطاً","Send a payment link":"أرسل رابط دفع","Take payment now":"استلم الدفعة الآن","Send 6 payment links":"أرسل ٦ روابط دفع","Card":"بطاقة","Cash":"نقداً","CliQ":"كليك","Total":"المجموع","Subtotal":"المجموع الفرعي","Book something else":"احجز شيئاً آخر","Add to my calendar":"أضف إلى تقويمي","Cancel this booking":"ألغِ هذا الحجز","Leave the waitlist":"اخرج من قائمة الانتظار","Download receipts":"حمّل الإيصالات","Replace this card":"استبدل هذه البطاقة","Add another card":"أضف بطاقة أخرى","Request my data":"اطلب بياناتي","Sign out everywhere else":"اخرج من الأجهزة الأخرى","Take a progress photo":"صوّر تقدّمك","Needs attention":"تحتاج انتباهاً","Today":"اليوم","All 14":"الكل · ١٤","Your clients":"عملاؤك","14 active · 3 need attention":"١٤ نشطاً · ٣ يحتاجون انتباهك","19 days since he trained":"مضى ١٩ يوماً على آخر تدريب","Session today 11:00":"حصة اليوم ١١:٠٠","Asked about her plan":"سألت عن خطتها","On track · week 5 of 12":"على المسار · الأسبوع ٥ من ١٢","Nutrition check-in overdue":"تأخر تقييم التغذية الأسبوعي","On track · week 9 of 12":"على المسار · الأسبوع ٩ من ١٢","BEFORE HE ARRIVES":"قبل أن يحضر","TODAY'S PLAN":"خطة اليوم","Session complete":"انتهت الحصة","WHAT THIS CONFIRMS":"ما يؤكده هذا","Book his next session":"احجز حصته القادمة","Add an exercise":"أضف تمريناً","Day A · lower body":"اليوم أ · الجسم السفلي","Search movements":"ابحث عن حركة","Recent":"الأحدث","Quads":"الأمامية","Hamstrings":"الخلفية","Available here":"المتوفر هنا","WEIGHT":"الوزن","STRENGTH":"القوة","PHOTOS":"الصور","Usually replies within a day":"يرد عادة خلال يوم","Write a reply":"اكتب رداً","Your week":"أسبوعك","9 sessions · 2 classes":"٩ حصص · صفّان","Set your availability":"حدّد أوقات عملك","Free":"متاح","22 sessions to verify":"٢٢ حصة بحاجة إلى توثيق","Back to 1 August":"حتى ١ آب","AVAILABILITY":"أوقات العمل","CERTIFICATIONS":"الشهادات","LANGUAGE":"اللغة","Lower-body strength":"قوة الجسم السفلي","Assign to Ahmad":"أسندها لأحمد","Assign the programme":"إسناد البرنامج","TO WHOM":"لمن","WHICH DAYS":"أي أيام","TELL HIM":"أبلغه","Now":"الآن","On Monday morning":"صباح الإثنين","New client":"عميل جديد","WHAT SHE WANTS":"ما تريده","Veyro Coach":"Veyro للمدربين","Email":"البريد الإلكتروني","Wednesday morning":"صباح الأربعاء","See the session":"اعرض الحصة","Your card expired":"انتهت صلاحية بطاقتك","Update my card instead":"حدّث بطاقتي بدلاً من ذلك","TODAY'S FOOD":"طعام اليوم","Ate something else →":"أكلت شيئاً آخر ←","Your bookings":"حجوزاتك","Your progress":"تقدّمك","Payments":"المدفوعات","Notifications":"التنبيهات","Privacy":"الخصوصية","Your pass":"تصريح الدخول","Your balance":"رصيدك","Your shopping":"قائمة الشراء","Weekly check-in":"التقييم الأسبوعي","How you pay":"كيف تدفع","Password and unlock":"كلمة السر وفتح التطبيق","Freeze your membership":"تجميد عضويتك","Freeze my membership":"جمّد عضويتي","Change my plan":"غيّر خطتي","Cancel membership":"إلغاء العضوية","What you want":"ما تريده","WHAT YOU GET":"ما تحصل عليه","YOUR AGREEMENT":"اتفاقيتك","WHAT YOU CAN LIFT":"ما ترفعه","WHAT YOU WANT":"ما تريده","FOOD":"الطعام","WHERE YOU ARE SIGNED IN":"الأجهزة المسجّلة","Face unlock":"فتح بالوجه","Change password":"تغيير كلمة السر","What you share, and with whom":"ما تشاركه، ومع من","What did you eat?":"ماذا أكلت؟","Scan a barcode":"امسح الباركود","Photograph your meal":"صوّر وجبتك","Looks right, log it":"صحيح، سجّلها","Let me correct it":"دعني أصحّحها","Log one bottle":"سجّل زجاجة واحدة","Book with Yousef":"احجز مع يوسف","What you have done":"ما أنجزته","Send to Yousef":"أرسل ليوسف","HOW DID THE WEEK GO":"كيف كان أسبوعك","Mostly stuck to it":"التزمت في الأغلب","Struggled":"واجهت صعوبة","ANYTHING HE SHOULD KNOW":"أي شيء يجب أن يعرفه","Optional":"اختياري","Send me a code":"أرسل لي رمزاً","Phone number":"رقم الهاتف","Ask Khalda to freeze it":"اطلب من خلدا التجميد","HOW LONG":"لكم من الوقت","1 month":"شهر واحد","2 months":"شهران","No signal down here":"لا تغطية هنا","WHAT WON'T WORK RIGHT NOW":"ما لا يعمل الآن","Find a member":"ابحث عن عضو","Guest entry":"دخول زائر","Start a trial":"ابدأ فترة تجريبية","Start her trial":"ابدأ فترتها التجريبية","Your equipment":"أجهزتك","Closing your shift":"إغلاق ورديتك","Close and hand over":"أغلق وسلّم","Sell a membership":"بِع عضوية","Personal training":"التدريب الشخصي","Refund":"استرداد","Receipt":"إيصال","Send by WhatsApp":"أرسل بالواتساب","Email it":"أرسله بالبريد","Tell maintenance":"أبلغ الصيانة","WHO":"من","WAIVER":"إقرار المسؤولية","Hand her the tablet":"أعطها الجهاز","Name":"الاسم","Phone":"الهاتف","Date of birth":"تاريخ الميلاد","Check in":"سجّل الدخول","WHAT STILL WORKS":"ما يعمل الآن","Ask Ziad to approve":"اطلب موافقة زياد","WITH WHICH COACH":"مع أي مدرب","A MANAGER HAS TO APPROVE THIS":"يحتاج موافقة مدير","Members":"الأعضاء","Leads":"العملاء المحتملون","Staff":"الموظفون","Reports":"التقارير","Revenue":"الإيرادات","Membership":"العضوية","Attendance":"الحضور","Products":"المنتجات","Stock":"المخزون","Discounts":"الخصومات","Tasks":"المهام","Automations":"الأتمتة","Access":"الدخول","Rooms":"القاعات","Turned away":"مُنعوا من الدخول","Organisation":"المؤسسة","Security":"الأمان","Your brand":"هويتك البصرية","Language and formats":"اللغة والتنسيقات","Connected services":"الخدمات المتصلة","Tax and invoicing":"الضرائب والفواتير","Message templates":"قوالب الرسائل","Message a group":"أرسل لمجموعة","Who gets told what":"من يُبلَّغ بماذا","Who can do what":"من يستطيع ماذا","Invite someone":"دعوة شخص","Add a lead":"أضف عميلاً محتملاً","Add a member":"أضف عضواً","Add her":"أضفها","Merge two records":"دمج سجلّين","Merge them":"ادمجهما","Take a payment":"استلم دفعة","Wallets and credits":"المحافظ والأرصدة","Partial refund":"استرداد جزئي","Cash reconciliation":"جرد النقد","Disputed charge":"مبلغ متنازع عليه","Book a PT session":"احجز حصة تدريب","Book it":"احجزها","Cancel Thursday spin":"ألغِ سبينينغ الخميس","Renew Ahmad Nabulsi":"جدّد لأحمد النابلسي","Plans and pricing":"الخطط والأسعار","Export as CSV":"صدّر كملف CSV","Export · needs a reason":"تصدير · يتطلب سبباً","Confirm and refund":"أكّد واسترد","Order 24":"اطلب ٢٤","Send the invitation":"أرسل الدعوة","Send the evidence":"أرسل الأدلة","Submit the evidence":"أرسل الأدلة","Close the shift":"أغلق الوردية","WHY":"السبب","AND OFFER THEM":"واعرض عليهم","WHAT WE READ":"ما قرأناه","WHAT THE NUMBERS SAY":"ما تقوله الأرقام","HOW VEYRO REACHED THIS":"كيف وصل Veyro إلى هذا","Open the 31 sessions":"افتح الحصص الـ٣١","Ask Khalda to verify them":"اطلب من خلدا توثيقها","BY CLUB":"حسب الفرع","WHEN PEOPLE COME":"متى يأتي الناس","WHY THE 23 LEFT":"لماذا ترك ٢٣ عضواً","RECENT":"الأحدث","TOTAL HELD":"الإجمالي المحتفظ به","Nothing needs you at Abdoun":"لا شيء يحتاجك في عبدون","New tenant":"مستأجر جديد","Member import":"استيراد الأعضاء","Subscription":"الاشتراك","Usage":"الاستخدام","Feature flags":"مفاتيح الميزات","System health":"حالة النظام","Audit log":"سجل التدقيق","Tenant billing":"فواتير المستأجرين","Veyro Console":"لوحة Veyro الداخلية","Message them":"أرسل لهم","Reply to Rania":"ردّ على رانيا","Open their data":"افتح بياناتهم","WHAT THEY HAVE":"ما لديهم","WHAT WE TOLD THEM":"ما أبلغناهم به","COLLECTED · MONTH TO DATE":"المحصّل · من بداية الشهر","ACTIVE MEMBERS":"الأعضاء النشطون","VISITS TODAY":"زيارات اليوم","LEAD CONVERSION · 30D":"تحويل العملاء · ٣٠ يوماً","IN THE BUILDING":"داخل النادي","CLASSES TODAY":"حصص اليوم","STAFF ON SHIFT":"الموظفون في الوردية","EXPIRING · 7 DAYS":"تنتهي خلال ٧ أيام","ENTRIES SINCE 09:04":"الدخول منذ ٠٩:٠٤","COLLECTED TODAY":"محصّل اليوم","OUTSTANDING":"المستحق","BALANCE":"الرصيد","RENEWS":"يتجدد","WALLET":"المحفظة","VISITS · 30D":"الزيارات · ٣٠ يوماً","MEMBERSHIP":"العضوية","ACCESS":"الدخول","NEXT BOOKING":"الحجز القادم","BILLING":"الفواتير","RESUMES":"يُستأنف","PT CREDITS":"حصص التدريب","LAST VISIT":"آخر زيارة","MRR":"الإيراد الشهري","HEALTH":"الحالة","VERSION":"الإصدار","IMPORTED":"مستورد","WAITING":"بالانتظار","REJECTED":"مرفوض","JOINED":"انضموا","LEFT":"تركوا","NET":"الصافي","MEMBERSHIPS":"العضويات","RETAIL":"التجزئة","PERSONAL TRAINING":"التدريب الشخصي","TURNED AWAY":"مُنعوا","DEVICES":"الأجهزة","ENTRIES TODAY":"الدخول اليوم","MEMBER":"العضو","PLAN":"الخطة","CLUB":"الفرع","STATE":"الحالة","AMOUNT":"المبلغ","SOURCE":"المصدر","AGE":"المدة","STAGE":"المرحلة","LEAD":"العميل المحتمل","INVOICE":"الفاتورة","PERIOD":"الفترة","PRODUCT":"المنتج","PRICE":"السعر","TAX":"الضريبة","ITEM":"الصنف","IN STOCK":"المتوفر","REORDER AT":"حد الطلب","WHEN":"الوقت","WHERE":"المكان","ROLE":"الدور","CLUBS":"الفروع","LAST ACTIVE":"آخر نشاط","TEMPLATE":"القالب","KIND":"النوع","RULE":"القاعدة","RUNS":"مرات التنفيذ","WHAT IT DID":"ما فعلته","RESULT":"النتيجة","ROOM":"القاعة","HOLDS":"السعة","EQUIPMENT":"التجهيزات","IN USE TODAY":"مستخدمة اليوم","TENANT":"المستأجر","ORIGIN":"المصدر","EXPIRES":"تنتهي","PAID":"مدفوعة","UNPAID · 2 DAYS":"غير مدفوعة · متأخرة يومين","OUT":"غير متوفر","LOW":"منخفض","OK":"جيد","ACTIVE":"نشط","FROZEN":"مجمّدة","OWES":"مستحق عليه","DENIED":"مُنع","RESOLVED":"محلولة","EXPIRED":"منتهية","BOOKED":"محجوز","ATTENDED":"حضر","CONNECTED":"متصل","GRANTED":"ممنوح","NOT GRANTED":"غير ممنوح","RECOVERED":"استُرد","WAITING FOR APPROVAL":"بانتظار الموافقة","FREE":"متاح","TAKEN":"محجوز","NO COACH":"بلا مدرب","SUBSTITUTED":"مُستبدل","SUBSTITUTE":"بديل","DONE":"تم","MONEY":"مالية","COMPLIANCE":"امتثال","RETENTION":"استمرارية العضوية","STAFFING":"الكوادر","LEADS":"عملاء محتملون","COACHING":"التدريب","Three things need you this morning":"ثلاثة أمور تحتاج انتباهك هذا الصباح","Needs you now":"يحتاج انتباهك الآن","6 payments failed overnight":"فشلت ٦ مدفوعات الليلة الماضية","JoFotara rejected 3 invoices":"رفضت جوفوترة ٣ فواتير","14 memberships expire within 7 days":"١٤ عضوية تنتهي خلال ٧ أيام","31 PT sessions delivered but not verified":"٣١ حصة تدريب نُفّذت دون توثيق","Spin has no coach and 18 members booked":"سبينينغ بلا مدرب و١٨ عضواً مسجّلون","Khalda · two things before the 09:00 rush":"خلدا · أمران قبل ذروة التاسعة","The turnstiles at Sweifieh are not reading cards":"بوابات الصويفية لا تقرأ البطاقات","Revenue analytics are 40 minutes behind":"تحليلات الإيرادات متأخرة ٤٠ دقيقة","Fix the 3 invoices":"صحّح الفواتير الثلاث","Review each":"راجع كل حالة","Send offer to the 9":"أرسل عرضاً للتسعة","Call list for the 5":"قائمة اتصال للخمسة","Assign now":"أسند الآن","Snooze":"تأجيل","unassigned":"غير مُسند","Open manual check-in":"افتح التسجيل اليدوي","Notify Sweifieh staff":"أبلغ موظفي الصويفية","Hardware status":"حالة الأجهزة","Apologise by WhatsApp":"اعتذر عبر الواتساب","Apologise to the 4":"اعتذر للأربعة","Ask both coaches to verify":"اطلب من المدربين التوثيق","Offer to Dana":"اعرضها على دانا","See both":"اعرض الاثنين","Show resolved today (7)":"إظهار ما تم حله اليوم (٧)","Load earlier activity":"تحميل نشاط أقدم","Save this view":"احفظ هذا العرض","Columns":"الأعمدة","Clear":"مسح","Send message":"أرسل رسالة","Send payment links":"أرسل روابط دفع","Add to segment":"أضف إلى مجموعة","Take payment · JOD 55.00":"استلم ٥٥٫٠٠ ديناراً","Mine":"مهامي","Everyone":"الجميع","Overdue":"متأخرة","All 34":"الكل · ٣٤","Low stock":"مخزون منخفض","Memberships":"العضويات","All 24":"الكل · ٢٤","Coaches":"المدربون","All 36":"الكل · ٣٦","No contact 48h":"بلا تواصل ٤٨ ساعة","Trial ending":"تنتهي التجربة","Popular":"الأكثر مبيعاً","Drinks":"المشروبات","Supplements":"المكمّلات","PT":"تدريب شخصي","Guest":"زائر","Just now":"الآن","live · last 10 minutes":"مباشر · آخر ١٠ دقائق","Quick sell":"بيع سريع","Your shift":"ورديتك","Waitlist · 3":"قائمة انتظار · ٣","Check someone in":"سجّل دخول شخص","Scan barcode":"امسح الباركود","Change method":"غيّر طريقة الدفع","Next sale":"البيع التالي","Try another card":"جرّب بطاقة أخرى","Take cash instead":"خذ نقداً بدلاً من ذلك","Queue this payment":"أدرج الدفعة في قائمة الانتظار","View the queue":"اعرض قائمة الانتظار","Present card":"قدّم البطاقة","Authorising":"جارٍ التحقق","Print receipt":"اطبع الإيصال","Month":"الشهر","7 days":"٧ أيام","usual for a Wednesday":"معتاد ليوم أربعاء","Show resolved today":"إظهار ما تم حله اليوم","at risk":"معرّضة للخطر","renewal value":"قيمة التجديد","Rania":"رانيا","Sales team":"فريق المبيعات","Nadia · accounts":"نادية · الحسابات","Open the class":"افتح الحصة","VEYRO INTERPRETATION · NOT A CONFIRMED FIGURE":"تحليل من Veyro · ليس رقماً مؤكداً","SYSTEM FACT":"واقعة مؤكدة","VEYRO'S READING OF WHY":"قراءة Veyro للأسباب","RECOMMENDED · YOU CONFIRM BEFORE ANYTHING RUNS":"إجراء مقترح · لا ينفّذ قبل موافقتك","See the evidence":"اعرض الأدلة","evidence":"الأدلة","By location · month to date":"حسب الفرع · من بداية الشهر","Khalda accounts for the entire shortfall. Abdoun and Sweifieh are both ahead of July.":"خلدا وحده يفسّر كامل التراجع. عبدون والصويفية متقدّمان على تموز.","Add member":"أضف عضواً","Owes money":"عليه مستحقات","Expiring":"قريبة الانتهاء","Not visited 30d":"لم يزر ٣٠ يوماً","Filter":"تصفية","selected":"محدّد","Collections · 12 weeks":"التحصيل · ١٢ أسبوعاً","weekly, all locations":"أسبوعياً · جميع الفروع","part wk":"أسبوع جزئي","Preview the request":"عاين الطلب","Show 4 lower-priority items":"إظهار ٤ بنود أقل أهمية","Wednesday 19 August · all locations · data through 08:38":"الأربعاء ١٩ آب · جميع الفروع · البيانات حتى ٠٨:٣٨","refresh":"تحديث","vs July · pace to 63.1k":"مقارنة بتموز","this month · 61 joined, 23 left":"هذا الشهر · انضم ٦١ وترك ٢٣","by 08:38 · usual for a Wednesday":"حتى ٠٨:٣٨ · معتاد ليوم أربعاء","target 30% · 36 open leads":"الهدف ٣٠٪ · ٣٦ عميلاً محتملاً","Sale · Ahmad Nabulsi":"بيع · أحمد النابلسي","CART · 3 ITEMS":"السلة · ٣ أصناف","Sales tax 16%":"ضريبة المبيعات ١٦٪","Tax on retail only · membership exempt":"الضريبة على التجزئة فقط · العضوية معفاة","Discount · needs manager":"خصم · يتطلب مديراً","Water 500ml":"ماء ٥٠٠ مل","Protein bar":"ألواح بروتين","Shaker":"شيكر","Towel hire":"استئجار منشفة","Whey 1kg":"واي بروتين ١ كغ","Day pass":"تصريح يومي","Creatine":"كرياتين","out of stock":"غير متوفر","Towel":"منشفة","capacity 180":"السعة ١٨٠","capacity 140":"السعة ١٤٠","all recorded at the desk":"كلها مسجّلة في الاستقبال","running normally":"تعمل بشكل طبيعي","unaffected":"غير متأثرة","live":"مباشر","as of 08:00":"حتى الساعة ٠٨:٠٠","Scan or type · focus is here":"امسح أو اكتب · المؤشر هنا","SCAN OR TYPE · FOCUS IS HERE":"امسح أو اكتب · المؤشر هنا","Card, phone, or name":"بطاقة أو هاتف أو اسم","Turnstile and app check-ins appear below automatically · no action needed":"دخول البوابات والتطبيق يظهر تلقائياً أدناه","Clean check-ins clear themselves after 10 minutes. Only the two above need you.":"الدخول السليم يُخفى تلقائياً بعد ١٠ دقائق. الحالتان أعلاه فقط تحتاجانك.","Mentioned it":"أبلغته","Send link instead":"أرسل رابطاً بدلاً من ذلك","Let in, flag for a call":"اسمح بالدخول وسجّل للمتابعة","One-day pass · 8.00":"تصريح يوم واحد · ٨٫٠٠","184 tenants · 3 need attention":"١٨٤ مستأجراً · ٣ يحتاجون انتباهاً","Affected now":"المتأثرون الآن","Notify the 3 tenants":"أبلغ المستأجرين الثلاثة","Provider status":"حالة المزوّد","Open incident":"افتح حادثة","Payment provider degraded · 3 tenants affected":"تراجع خدمة مزوّد الدفع · ٣ مستأجرين متأثرون","Four expired cards, two insufficient funds. Veyro retried each twice and drafted a message for every member. No access is blocked — all six can train today.":"أربع بطاقات منتهية الصلاحية، واثنتان برصيد غير كافٍ. أعاد Veyro المحاولة مرتين لكل حالة وجهّز رسالة لكل عضو. لم يُمنع أي دخول — الستة جميعاً يمكنهم التدريب اليوم.","All three are missing a buyer tax number. The sales are recorded and the money is collected — only the e-invoice submission failed. Correct the field and they resubmit automatically.":"الثلاث تنقصها الرقم الضريبي للمشتري. المبيعات مسجّلة والمبالغ محصّلة — الإرسال الإلكتروني وحده هو ما فشل. صحّح الحقل وسيُعاد الإرسال تلقائياً.","Nine have trained in the last fortnight and historically renew without prompting. Five have not visited in over 20 days — those are the ones worth a call.":"تسعة منهم تدرّبوا خلال الأسبوعين الماضيين ويجدّدون عادة دون تذكير. خمسة لم يزوروا النادي منذ أكثر من ٢٠ يوماً — هؤلاء من يستحقون مكالمة.","What is JoFotara?":"ما هي جوفوترة؟","since 09:14 yesterday · Sweifieh":"منذ ٠٩:١٤ أمس · الصويفية","Spin 19:00 Thursday has no coach — 18 members booked":"حصة السبينينغ الخميس ١٩:٠٠ بلا مدرب — ١٨ عضواً مسجّلون","Open any item for its full evidence and history →":"افتح أي بند لعرض أدلته وسجله الكامل ←","Collections are JOD 3,490 below the same point in July.":"المبالغ المحصّلة أقل بمقدار JOD 3,490 من الفترة نفسها في تموز.","Khalda accounts for the entire shortfall.":"خلدا وحده يفسّر كامل التراجع.","Khalda accounts for the entire shortfall — the unverified PT sessions are most of it. Abdoun and Sweifieh are both ahead of July.":"خلدا وحده يفسّر كامل التراجع — وحصص التدريب غير الموثّقة هي معظمه. عبدون والصويفية متقدّمان على تموز.","Nothing here enumerates 4,812 rows. Filters query server-side and the count states matches against total.":"لا شيء هنا يعرض ٤٨١٢ صفاً. التصفية تُنفَّذ على الخادم، والعدد يوضّح المطابق مقابل الإجمالي.","Showing 0 matching · 4,812 total":"عرض ٠ مطابق · ٤٨١٢ إجمالاً","Export · needs approval":"تصدير · يتطلب موافقة","August to date · all clubs":"من بداية آب · جميع الفروع","COLLECTED":"المحصّل","down 7.8% on July":"أقل بنسبة ٧٫٨٪ من تموز","down 1,840":"أقل بـ١٨٤٠","up 4%":"أعلى بنسبة ٤٪","FRONT DESK":"الاستقبال","REGISTER":"الصندوق","Member lookup":"البحث عن عضو","Guest & day pass":"الزوار والتصاريح اليومية","Class check-in":"تسجيل دخول الحصص","Shift":"الوردية","Sale":"بيع","Membership sale":"بيع عضوية","PT package":"باقة تدريب شخصي","Receipts":"الإيصالات","Split":"تقسيم","Apply 10% discount":"طبّق خصم ١٠٪","Club · wallet JOD 12.50":"كلب · المحفظة JOD 12.50","Club membership · August":"عضوية كلب · آب","Lower body\nat 09:45":"الجسم السفلي\nالساعة ٠٩:٤٥","With Yousef. It's been a while — he's planning to start lighter than last time.":"مع يوسف. مضى وقت طويل — ينوي البدء بوزن أخف من المرة الماضية.","August's JOD 55.00 didn't go through. You can still train — sort it whenever.":"لم تُنفَّذ دفعة آب بمقدار JOD 55.00. يمكنك التدريب كالمعتاد — سدّدها وقتما تشاء.","Pay JOD 55.00":"ادفع JOD 55.00","OF 2,150 KCAL":"من ٢١٥٠ سعرة","BREAKFAST":"الفطور","LUNCH · 13:00":"الغداء · ١٣:٠٠","AFTER TRAINING · 18:15":"بعد التدريب · ١٨:١٥","EATEN":"تم تناولها","Oats, banana, whey":"شوفان وموز وواي بروتين","Chicken with rice and yoghurt":"دجاج مع أرز ولبن","Whey and dates":"واي بروتين وتمر","Provisioning":"التهيئة","Card authorisations failing intermittently in Jordan since 08:52. Cash, CliQ and check-in unaffected everywhere. 41 failed authorisations, all queued for retry, none charged twice.":"تعطّل متقطع في تفويض البطاقات في الأردن منذ ٠٨:٥٢. النقد وكليك وتسجيل الدخول غير متأثرة في كل الفروع. ٤١ عملية تفويض فاشلة، جميعها في قائمة إعادة المحاولة، ولم يُخصم من أحد مرتين.","Open the incident":"افتح الحادثة","MRR JOD 148,200 · 11 in onboarding · 2 churn risks":"الإيراد الشهري JOD 148,200 · ١١ في التهيئة · ٢ معرّضان للمغادرة","Growth":"النمو","Enterprise":"المؤسسات","Starter":"المبتدئة","AT RISK":"معرّض للخطر","ONBOARDING":"قيد التهيئة","day 4 · import pending":"اليوم ٤ · الاستيراد معلّق","No member data on this screen. Counts and health signals only — an engineer can see that Nadi Group had 18 authorisation failures, not who they were. Opening a tenant’s own data requires an impersonation session with a stated reason, a time limit, and a line in the audit log the tenant can read.":"لا توجد بيانات أعضاء على هذه الشاشة. أعداد ومؤشرات حالة فقط — يرى المهندس أن مجموعة نادي لديها ١٨ عملية تفويض فاشلة، لا من هم أصحابها. فتح بيانات المستأجر يتطلب جلسة انتحال هوية بسبب معلَن ومدة محددة وسطر في سجل التدقيق يستطيع المستأجر قراءته.","target 30% · 36 open":"الهدف ٣٠٪ · ٣٦ مفتوحاً","month to date":"من بداية الشهر","FAILED":"فاشلة","REFUNDED":"مستردة","PENDING":"معلّقة","METHOD":"طريقة الدفع","JOFOTARA":"جوفوترة","not submitted":"لم تُرسل","submitted":"أُرسلت","Open the recovery workspace":"افتح مساحة الاسترداد","Fix the rejected e-invoice":"صحّح الفاتورة المرفوضة","Club · card ···8841 · 18:42":"كلب · بطاقة ···8841 · ١٨:٤٢","OWES JOD 55.00":"مستحق عليه JOD 55.00","Let him in. His card expired and he owes 55 dinars — mention it warmly, offer to settle now. He can train until 2 September either way.":"اسمح له بالدخول. بطاقته منتهية وعليه ٥٥ ديناراً — اذكر ذلك بلطف واعرض تسديدها الآن. يمكنه التدريب حتى ٢ أيلول في الحالتين.","Take JOD 55.00":"استلم JOD 55.00","Flex · app pass · 18:39":"فليكس · تصريح التطبيق · ١٨:٣٩","EXPIRED 12 DAYS AGO":"انتهت قبل ١٢ يوماً","Resolve this":"حلّ هذه الحالة","Club+ · turnstile · 18:41":"كلب بلس · البوابة · ١٨:٤١","Club · app · 18:40":"كلب · التطبيق · ١٨:٤٠","Ahmad · lower body":"أحمد · الجسم السفلي","His membership ended on 7 August. Grace ran out five days ago. He was here three times a week for two years — worth asking whether something changed rather than leading with the renewal.":"انتهت عضويته في ٧ آب، وانتهت فترة السماح قبل خمسة أيام. كان يأتي ثلاث مرات أسبوعياً لعامين — يستحق أن تسأله إن تغيّر شيء قبل أن تبدأ بالتجديد.","Renew · Flex JOD 40.00":"جدّد · فليكس JOD 40.00","27 min · exercise 3 of 5":"٢٧ دقيقة · التمرين ٣ من ٥","Back squat":"سكوات خلفي","Box squat":"سكوات على صندوق","Romanian deadlift":"رفعة رومانية","Leg press":"دفع الأرجل","Walking lunge":"خطوات أمامية","Calf raise":"رفع السمانة","Front squat":"سكوات أمامي","Split squat":"سكوات منفصل","Leg curl":"ثني الأرجل","Rest 2:00 starts when you log":"راحة ٢:٠٠ تبدأ عند التسجيل","Everything logs offline · syncs when you leave the basement":"كل شيء يُسجّل دون اتصال · يُرسل عند خروجك من القبو","Voice note · 14s · transcribed · saved to his record":"ملاحظة صوتية · ١٤ ثانية · مكتوبة · محفوظة في سجله","He stopped at 5 on set 2 and said his knee felt tight. Dropped him to 75 rather than pushing to 82.5.":"توقف عند ٥ تكرارات في المجموعة الثانية وقال إن ركبته مشدودة. أنزلته إلى ٧٥ بدلاً من الدفع إلى ٨٢٫٥.","Club · monthly · JOD 55.00":"كلب · شهرية · JOD 55.00","Renews 21 Aug, auto":"تتجدد ٢١ آب تلقائياً","A 12-month commitment ends in March. Cancelling before then carries a two-month fee.":"التزام ١٢ شهراً ينتهي في آذار. الإلغاء قبل ذلك يترتب عليه رسم شهرين.","Yousef · 4 credits left":"يوسف · ٤ حصص متبقية","Operational context only. Programme detail, logs and plan content live in Coach.":"سياق تشغيلي فقط. تفاصيل البرنامج والسجلات والخطة في تطبيق المدرب.","Biometric data is never displayed or exportable — only whether enrolment exists. Removing it needs owner approval.":"بيانات البصمة لا تُعرض ولا تُصدَّر — تظهر حالة التسجيل فقط. حذفها يتطلب موافقة المالك.","Card ···8841 · active":"بطاقة ···8841 · نشطة","App pass · active":"تصريح التطبيق · نشط","Fingerprint · enrolled":"البصمة · مسجّلة","Programme: Lower-body strength, week 8 of 12. On a nutrition plan reviewed 4 Aug.":"البرنامج: قوة الجسم السفلي، الأسبوع ٨ من ١٢. على خطة غذائية روجعت في ٤ آب.","RECEIPT":"الإيصال","CREDIT NOTE":"إشعار دائن","Paid 1 Jul":"دُفعت ١ تموز","Paid 1 Jun":"دُفعت ١ حزيران","Paid 14 Jan":"دُفعت ١٤ كانون الثاني","NOT PAID YET":"لم تُدفع بعد","PT · 10 sessions":"تدريب شخصي · ١٠ حصص","Use it at the desk or for classes. The 12.50 from the cancelled yoga class expires 14 November.":"استخدمه في الاستقبال أو للحصص. مبلغ ١٢٫٥٠ من حصة اليوغا الملغاة ينتهي في ١٤ تشرين الثاني.","Class credit · Yoga cancelled":"رصيد حصة · يوغا ملغاة","Spent on water":"صُرف على ماء","Top-up":"إضافة رصيد","Support · impersonation started":"الدعم · بدأت جلسة انتحال هوية","Nadi Group · read only · ticket #4182":"مجموعة نادي · قراءة فقط · تذكرة #4182","Immutable. Impersonation entries are highlighted and visible to the tenant in their own audit log.":"غير قابل للتغيير. جلسات انتحال الهوية مميّزة وظاهرة للمستأجر في سجل التدقيق الخاص به.","All tenants · last 48 hours":"جميع المستأجرين · آخر ٤٨ ساعة","last: 82.5 × 5":"آخر مرة: ٨٢٫٥ × ٥","Finish and verify":"أنهِ ووثّق","Club membership · Khalda":"عضوية كلب · خلدا","August":"آب","July":"تموز","June":"حزيران","Yesterday":"أمس","Pay August · JOD 55.00":"ادفع آب · JOD 55.00","Payment history and receipts":"سجل المدفوعات والإيصالات","Support · feature flag changed":"الدعم · تغيير مفتاح ميزة","Arabic Coach app → Nadi Group":"تطبيق المدرب بالعربية ← مجموعة نادي","Support · export":"الدعم · تصدير","Tenant list · reason logged":"قائمة المستأجرين · السبب مسجّل","Wednesday 19 August · your club · data through 08:38":"الأربعاء ١٩ آب · فرعك · البيانات حتى ٠٨:٣٨","What Ziad does not see: group revenue, cross-location comparison, the JoFotara queue, or the recovery workflow itself. Enough to answer a question at the desk, without financial administration he cannot act on.":"ما لا يراه زياد: إيرادات المجموعة، والمقارنة بين الفروع، وقائمة جوفوترة، ومسار استرداد المدفوعات نفسه. ما يكفي للإجابة عن سؤال في الاستقبال، دون إدارة مالية لا يستطيع التصرف بها.","The access controller stopped responding at 09:04. Members cannot enter with a card or the app. Check-in at the desk still works and every entry is recorded, so nothing is lost. Bookings, payments and classes are unaffected.":"توقّف جهاز التحكم بالدخول عن الاستجابة الساعة ٠٩:٠٤. لا يستطيع الأعضاء الدخول بالبطاقة أو التطبيق. التسجيل في الاستقبال يعمل وكل دخول يُسجّل، فلا شيء يُفقد. الحجوزات والمدفوعات والحصص غير متأثرة.","Retrying every 30s · 16 minutes elapsed · stays visible until the controller responds":"إعادة المحاولة كل ٣٠ ثانية · مضت ١٦ دقيقة · يظل ظاهراً حتى يستجيب الجهاز","Why the metrics stay neutral: 48 people in the building is a fact, not a problem. Colouring it red during an unrelated outage teaches staff to distrust the colour.":"لماذا تبقى المؤشرات محيّدة: وجود ٤٨ شخصاً في النادي واقعة لا مشكلة. تلوينها بالأحمر أثناء عطل غير ذي صلة يعلّم الموظفين عدم الثقة باللون.","Payments, access, bookings and staffing are all clear. Last checked 14:20.":"المدفوعات والدخول والحجوزات والكوادر كلها سليمة. آخر تحقق ١٤:٢٠.","NEW LEADS":"عملاء محتملون جدد","CLASS FILL":"نسبة امتلاء الحصص","Review this week's renewals":"راجع تجديدات هذا الأسبوع","No illustration and no \"all caught up!\" — it reports the day and offers the next useful thing. A manager seeing this should feel informed, not congratulated.":"لا رسوم ولا عبارة «أنجزت كل شيء» — تقرير عن اليوم وعرض لأنفع خطوة تالية. المدير الذي يرى هذا يجب أن يشعر بأنه مطّلع، لا بأنه يُهنّأ.","The reporting pipeline is catching up after overnight maintenance. Figures shown are correct as of 08:00 — they are not wrong, only late. Attention items, member records and payments are live.":"خط التقارير يستدرك بعد صيانة ليلية. الأرقام المعروضة صحيحة حتى الساعة ٠٨:٠٠ — ليست خاطئة، بل متأخرة. بنود الانتباه وسجلات الأعضاء والمدفوعات مباشرة.","Next attempt in 4 minutes":"المحاولة التالية بعد ٤ دقائق","COLLECTED · MTD":"المحصّل · من بداية الشهر","LEAD CONVERSION":"تحويل العملاء المحتملين","AI PANEL · WITHHELD":"لوحة التحليل · محجوبة","Veyro is not offering a revenue interpretation while the underlying figures are stale. It will return when the pipeline catches up.":"لا يقدّم Veyro تحليلاً للإيرادات بينما الأرقام الأساسية قديمة. سيعود عند استدراك خط التقارير.","Per-panel provenance, not a page-level spinner. Stale numbers de-emphasise and carry a timestamp; live ones stay primary. An interpretation built on stale inputs is worse than no interpretation.":"بيان مصدر لكل لوحة، لا مؤشر تحميل للصفحة كلها. الأرقام القديمة تُخفَّف ويُذكر وقتها؛ والمباشرة تبقى في المقدمة. تحليل مبني على بيانات قديمة أسوأ من لا تحليل.","WHAT HAPPENED":"ما حدث","WHAT IS AFFECTED":"ما تأثّر","WHAT YOU CAN DO":"ما يمكنك فعله","Six scheduled membership charges failed between 06:00 and 06:12. Four cards had expired, two had insufficient funds. Veyro retried each twice on the schedule set in dunning configuration and stopped, as configured, rather than retrying indefinitely.":"فشلت ست عمليات خصم مجدولة للعضويات بين ٠٦:٠٠ و٠٦:١٢. أربع بطاقات منتهية واثنتان برصيد غير كافٍ. أعاد Veyro المحاولة مرتين لكل حالة وفق الجدول المحدد في إعدادات المتابعة ثم توقّف كما هو مُعَدّ، بدل المحاولة إلى ما لا نهاية.","Assign to Nadia":"أسندها لنادية","Snooze 24h":"تأجيل ٢٤ ساعة","ACTION HISTORY":"سجل الإجراءات","Charges attempted · 6 of 218 failed":"محاولات الخصم · فشلت ٦ من ٢١٨","Retry 1 · all 6 declined":"المحاولة ١ · رُفضت الست جميعاً","Retry 2 · all 6 declined · dunning stopped":"المحاولة ٢ · رُفضت الست · توقفت المتابعة","Messages drafted, awaiting approval":"جُهّزت الرسائل وتنتظر الموافقة","Raised to the Command Center":"رُفعت إلى مركز القيادة","Resolved today":"حُلّت اليوم","Low stock · Khalda":"مخزون منخفض · خلدا","Reordered":"أُعيد الطلب","Document expiry · 3 waivers":"انتهاء وثائق · ٣ إقرارات","Members messaged":"تم مراسلة الأعضاء","Coach note · Omar":"ملاحظة مدرب · عمر","Acknowledged":"تم الاطلاع","Failed payment · Hala":"دفعة فاشلة · هالة","Link sent, paid":"أُرسل الرابط ودُفع","Access denial · Tareq":"منع دخول · طارق","Day pass sold":"بيع تصريح يومي","Lead uncontacted · 4":"عملاء بلا تواصل · ٤","Sales":"المبيعات","Assigned":"مُسند","Class capacity · Yoga":"سعة حصة · يوغا","Waitlist opened":"فُتحت قائمة الانتظار","No un-resolve action exists. A resolution is a record — correcting one means acting again, which appears here as a new row.":"لا يوجد إجراء لإلغاء الحل. الحل سجل — وتصحيحه يعني إجراءً جديداً يظهر هنا كصف جديد.","New":"جديد","open day · 2d":"يوم مفتوح · قبل يومين","instagram · 4h":"إنستغرام · قبل ٤ ساعات","Contacted":"تم التواصل","called · 1d":"مكالمة · قبل يوم","Toured":"زار النادي","Mon 17:00":"الإثنين ١٧:٠٠","On trial":"في فترة تجريبية","day 6 of 7":"اليوم ٦ من ٧","Joined":"انضم","NO CONTACT · 2 DAYS":"بلا تواصل · يومان","Sweifieh open day · +962 79 411 0288 · interested in classes and PT":"يوم الصويفية المفتوح · +962 79 411 0288 · مهتمة بالحصص والتدريب الشخصي","Sweifieh open day · 079 411 0288 · interested in classes and PT":"يوم الصويفية المفتوح · 079 411 0288 · مهتمة بالحصص والتدريب الشخصي","Start a 7-day trial":"ابدأ فترة تجريبية ٧ أيام","VEYRO SUGGESTS · YOU SEND IT":"يقترح Veyro · وأنت من يرسل","VEYRO SUGGESTS · YOU DECIDE":"يقترح Veyro · والقرار لك","She asked about the 19:00 spin class twice at the open day. Offer the trial with a spin booking already held — 4 of the 11 who joined this month came in through a class, not a tour.":"سألت مرتين عن حصة السبينينغ ١٩:٠٠ في اليوم المفتوح. اعرض الفترة التجريبية مع حجز سبينينغ محفوظ لها — ٤ من ١١ انضموا هذا الشهر جاؤوا عبر حصة لا عبر زيارة.","She asked about the 19:00 spin class twice at the open day and mentioned she works in Abdoun. Four of the eleven who joined this month came in through a class, not a tour.":"سألت مرتين عن حصة السبينينغ ١٩:٠٠ في اليوم المفتوح وذكرت أنها تعمل في عبدون. أربعة من أحد عشر انضموا هذا الشهر جاؤوا عبر حصة لا عبر زيارة.","Sweifieh open day":"يوم الصويفية المفتوح","No contact":"بلا تواصل","Instagram":"إنستغرام","Referral · Dana":"ترشيح · دانا","Called":"تم الاتصال","Walk-in":"زيارة مباشرة","Google":"جوجل","On trial · day 6":"فترة تجريبية · اليوم ٦","Sales sees their own leads by default. Ziad sees the whole club. Nobody sees another club unless their role spans it.":"يرى فريق المبيعات عملاءه افتراضياً. يرى زياد الفرع بكامله. ولا أحد يرى فرعاً آخر إلا إذا كان دوره يشمله.","Registered at the Sweifieh open day":"سُجّلت في يوم الصويفية المفتوح","Asked about the 19:00 spin class twice":"سألت مرتين عن حصة السبينينغ ١٩:٠٠","Added to Layla’s list":"أُضيفت إلى قائمة ليلى","Automatic · open-day source":"تلقائي · مصدره اليوم المفتوح","Automated welcome message sent":"أُرسلت رسالة ترحيب تلقائية","Delivered, not opened":"وصلت ولم تُفتح","Offer the trial with a spin booking already held":"اعرض الفترة التجريبية مع حجز سبينينغ محفوظ","Preview the message":"عاين الرسالة","Just the trial":"الفترة التجريبية فقط","PHONE":"الهاتف","WHERE FROM":"المصدر","INTERESTED IN":"مهتم بـ","Classes, personal training":"الحصص والتدريب الشخصي","Name and phone is enough. A lead captured badly beats a lead not captured — the rest can be filled in later.":"الاسم والهاتف يكفيان. تسجيل ناقص أفضل من عدم التسجيل — والبقية تُكمل لاحقاً.","VISITS":"الزيارات","of 7 days":"من ٧ أيام","CLASSES":"الحصص","all spin":"كلها سبينينغ","TRIAL ENDS":"تنتهي التجربة","tomorrow":"غداً","CONVERSION LIKELIHOOD":"احتمال التحويل","High":"مرتفع","class-led, 4 visits":"مدفوعة بالحصص · ٤ زيارات","Her trial ends tomorrow":"تنتهي فترتها التجريبية غداً","Four visits and three spin classes in six days. Members who attend three or more classes on trial convert at 68% here. Club is the fit — Flex would exclude the classes she actually came for.":"أربع زيارات وثلاث حصص سبينينغ في ستة أيام. من يحضر ثلاث حصص أو أكثر في التجربة يتحوّل بنسبة ٦٨٪ في هذا الفرع. كلب هي الأنسب — فليكس تستثني الحصص التي جاءت من أجلها.","Convert to Club":"حوّلها إلى كلب","Extend the trial 3 days":"مدّد التجربة ٣ أيام","Mark lost":"سجّلها كمفقودة","Convert Rana to a member":"حوّل رنا إلى عضوة","CARRIED FORWARD FROM HER TRIAL":"ما يُنقل من فترتها التجريبية","Name, phone, waiver acceptance, emergency contact, her 4 check-ins, her 3 spin bookings, and the note from the open day. Same record ID — M-04913 was issued when the trial started.":"الاسم والهاتف وقبول الإقرار وجهة الاتصال للطوارئ، وزياراتها الأربع، وحجوزاتها الثلاثة للسبينينغ، وملاحظة اليوم المفتوح. نفس رقم السجل — صدر M-04913 عند بدء التجربة.","WHAT YOU CHOOSE NOW":"ما تختاره الآن","Plan, term, start date, payment method. Four fields.":"الخطة والمدة وتاريخ البدء وطريقة الدفع. أربعة حقول.","Open the sale sheet":"افتح نموذج البيع","This is the duplicate-data-entry fix from the Phase 6 review, made structural: a lead, a trialist and a member are one record at three stages.":"هذا هو حل تكرار إدخال البيانات من مراجعة المرحلة السادسة، مُطبَّقاً بنيوياً: العميل المحتمل والمتدرّب تجريبياً والعضو سجل واحد في ثلاث مراحل.","Mark Tareq Fayez as lost":"سجّل طارق فايز كمفقود","Instagram · 8 days · never contacted":"إنستغرام · ٨ أيام · لم يُتواصل معه","Too expensive":"السعر مرتفع","Joined somewhere else":"انضم لمكان آخر","Never replied":"لم يرد","Wrong number":"رقم خطأ","Not ready yet":"ليس مستعداً بعد","This feeds the source report — eight days without contact is what lost him, and Instagram leads going cold is a pattern worth seeing. He can be reopened after 90 days.":"هذا يغذّي تقرير المصادر — ثمانية أيام بلا تواصل هي ما أفقدنا إياه، وبرود عملاء إنستغرام نمط يستحق الملاحظة. يمكن إعادة فتح سجله بعد ٩٠ يوماً.","Mark as lost":"سجّله كمفقود","PAYMENT OVERDUE":"دفعة متأخرة","Club · Khalda · member since March 2024 · M-04188":"كلب · خلدا · عضو منذ آذار ٢٠٢٤ · M-04188","Overview":"نظرة عامة","Billing":"الفواتير","Coaching":"التدريب","Documents":"الوثائق","Timeline":"السجل الزمني","His card expired and JOD 55.00 is unpaid":"انتهت بطاقته ومبلغ JOD 55.00 غير مدفوع","Retried on the 17th and 18th. His access is unaffected — 14 days of grace, so he can train until 2 September.":"أُعيدت المحاولة في ١٧ و١٨. دخوله غير متأثر — مهلة ١٤ يوماً، فيمكنه التدريب حتى ٢ أيلول.","Open the invoice":"افتح الفاتورة","Payment failed — card expired":"فشل الدفع — البطاقة منتهية","Veyro · third attempt · INV-20418 · JOD 55.00":"Veyro · المحاولة الثالثة · INV-20418 · JOD 55.00","Payment reminder drafted, not sent":"جُهّزت رسالة تذكير ولم تُرسل","Awaiting your approval":"بانتظار موافقتك","PT session with Yousef · verified":"حصة تدريب مع يوسف · موثّقة","Checked in · Khalda":"دخل النادي · خلدا","Health notes updated by Dr. Samar":"حدّثت د. سمر الملاحظات الصحية","Clinical content is not shown here":"المحتوى الطبي لا يُعرض هنا","Withdrew marketing consent":"سحب موافقته على الرسائل التسويقية","Service messages still allowed":"رسائل الخدمة لا تزال مسموحة","Operational context only. Programme detail lives in Coach.":"سياق تشغيلي فقط. تفاصيل البرنامج في تطبيق المدرب.","Card ···8841 active · app pass active · fingerprint enrolled":"بطاقة ···8841 نشطة · تصريح التطبيق نشط · البصمة مسجّلة","Biometric data is never displayed or exportable.":"بيانات البصمة لا تُعرض ولا تُصدَّر.","Club+ · Khalda · since Jan 2023 · M-02914":"كلب بلس · خلدا · منذ كانون الثاني ٢٠٢٣ · M-02914","automatically":"تلقائياً","three a week":"ثلاث مرات أسبوعياً","expires Nov":"تنتهي تشرين الثاني","Card at the turnstile":"بالبطاقة على البوابة","PT with Yousef · verified":"تدريب مع يوسف · موثّق","Membership renewed · Club+":"تجديد العضوية · كلب بلس","No green badges. Paid, active and granted are the expected cases — decorating them makes a genuinely overdue row harder to spot. The absence of an alert band is the signal.":"لا شارات خضراء. المدفوع والنشط والمسموح هي الحالات المتوقعة — وتزيينها يجعل الصف المتأخر فعلاً أصعب في الملاحظة. غياب شريط التنبيه هو الإشارة.","Club · Khalda · 079 555 0134":"كلب · خلدا · 079 555 0134","He owes JOD 55.00 — mention it, don’t block him":"عليه JOD 55.00 — اذكر ذلك ولا تمنعه","His card expired. He can train until 2 September. Offer to take payment at the desk or send him a link.":"بطاقته منتهية. يمكنه التدريب حتى ٢ أيلول. اعرض استلام الدفعة في الاستقبال أو أرسل له رابطاً.","Granted":"مسموح","grace to 2 Sep":"مهلة حتى ٢ أيلول","expires":"تنتهي","None":"لا يوجد","VISITS AND PAYMENTS ONLY":"الزيارات والمدفوعات فقط","Payment failed":"فشل الدفع","Absent, not greyed: no coaching panel, no health notes, no PT credits, no commitment terms, no refund action. Layla sees what she needs to greet him and take his money.":"غائب لا معطّل: لا لوحة تدريب، ولا ملاحظات صحية، ولا حصص تدريب، ولا شروط التزام، ولا إجراء استرداد. ترى ليلى ما تحتاجه لاستقباله واستلام دفعته.","Club+ · Abdoun · since Jun 2022":"كلب بلس · عبدون · منذ حزيران ٢٠٢٢","Frozen until 1 October · travel":"مجمّدة حتى ١ تشرين الأول · سفر","Approved by Rania on 28 July. Billing is paused, access is off, and her Club+ rate is held. She has used 2 of 3 freeze months this year.":"وافقت رانيا في ٢٨ تموز. الفواتير موقوفة والدخول مغلق وسعر كلب بلس محفوظ لها. استخدمت شهرين من ثلاثة للتجميد هذا العام.","Resume early":"استئناف مبكر","Extend · needs approval":"تمديد · يتطلب موافقة","Paused":"موقوفة","Off":"مغلق","by agreement":"باتفاق","Frozen is info severity, not warning — a normal agreed arrangement, not a problem. Access reads \"Off\", never \"Denied\": denied means something went wrong, off means someone chose it.":"التجميد حالة معلوماتية لا تحذيرية — ترتيب متفق عليه لا مشكلة. الدخول يُكتب «مغلق» لا «مُنع»: المنع يعني خللاً، والإغلاق يعني قراراً.","Club · JOD 55.00 monthly":"كلب · JOD 55.00 شهرياً","HOW HE PAYS":"كيف يدفع","No backup is why this failed three times rather than once.":"عدم وجود بديل هو ما جعلها تفشل ثلاث مرات لا مرة واحدة.","LAST 12 WEEKS":"آخر ١٢ أسبوعاً","Three a week for eight weeks, then nothing for three. No message, no cancellation — he just stopped.":"ثلاث مرات أسبوعياً لثمانية أسابيع، ثم لا شيء لثلاثة. لا رسالة ولا إلغاء — توقّف فقط.","Card · last visit":"بالبطاقة · آخر زيارة","App pass":"تصريح التطبيق","One expiring":"واحدة قاربت الانتهاء","Membership agreement":"اتفاقية العضوية","Signed 4 Mar 2024":"وُقّعت ٤ آذار ٢٠٢٤","v3":"الإصدار ٣","Health questionnaire":"الاستبيان الصحي","Completed 4 Mar 2024":"اكتُمل ٤ آذار ٢٠٢٤","Photo ID":"إثبات الهوية","Uploaded 4 Mar 2024":"رُفع ٤ آذار ٢٠٢٤","Medical clearance":"الإخلاء الطبي","Expires 12 Sep 2026":"تنتهي ١٢ أيلول ٢٠٢٦","The medical clearance expiry raises a Command Center item three weeks out. Medical documents are visible only to roles with health permission — Layla sees the row exists, not the file.":"انتهاء الإخلاء الطبي يرفع بنداً في مركز القيادة قبل ثلاثة أسابيع. الوثائق الطبية مرئية فقط للأدوار ذات صلاحية صحية — ترى ليلى وجود الصف لا الملف.","STAFF NOTES · NEVER VISIBLE TO THE MEMBER":"ملاحظات الموظفين · لا تظهر للعضو أبداً","Called about the failed payment, no answer. Will try again Thursday.":"اتصلت بشأن الدفعة الفاشلة، لا رد. سأحاول الخميس.","Asked whether he could freeze rather than cancel. Explained the options.":"سأل إن كان يمكنه التجميد بدل الإلغاء. شرحت له الخيارات.","CONSENT":"الموافقات","Marketing withdrawn 12 July. Service messages about payments, bookings and access are still permitted.":"سُحبت الموافقة التسويقية في ١٢ تموز. رسائل الخدمة عن المدفوعات والحجوزات والدخول لا تزال مسموحة.","Open the WhatsApp thread":"افتح محادثة الواتساب","Walk-in · Khalda":"زيارة مباشرة · خلدا","EMAIL":"البريد الإلكتروني","DATE OF BIRTH":"تاريخ الميلاد","EMERGENCY CONTACT":"جهة الاتصال للطوارئ","No existing record matches 079 555 0134. If one did, we would offer it rather than creating a second Sara Halabi.":"لا يوجد سجل مطابق للرقم 079 555 0134. لو وُجد لعرضناه بدل إنشاء سارة حلبي ثانية.","Add her, then sell a membership":"أضفها ثم بِع عضوية","FIELD":"الحقل","Plan":"الخطة","Club · active":"كلب · نشطة","Flex · never paid":"فليكس · لم تُدفع","Visits":"الزيارات","THIS CANNOT BE UNDONE":"لا يمكن التراجع عن هذا","Payment history from both always merges. Type the surviving member ID to confirm.":"سجل المدفوعات من السجلين يُدمج دائماً. اكتب رقم العضو الباقي للتأكيد.","CONFIRM THE ID YOU ARE KEEPING":"أكّد الرقم الذي تُبقيه","Off-peak · no classes":"خارج أوقات الذروة · بلا حصص","All hours · classes included":"جميع الأوقات · الحصص مشمولة","All clubs · 2 PT monthly":"جميع الفروع · حصتا تدريب شهرياً","Today · pro-rata to 31 Aug":"اليوم · بالتناسب حتى ٣١ آب","Then monthly from 1 Sep":"ثم شهرياً من ١ أيلول","Monthly rolling — cancel any time with 30 days notice. No commitment fee.":"شهرية متجددة — يمكن الإلغاء في أي وقت بإشعار ٣٠ يوماً. بلا رسم التزام.","Take payment · 21.29":"استلم الدفعة · ٢١٫٢٩","Send a link":"أرسل رابطاً","Club · expires 21 August":"كلب · تنتهي ٢١ آب","THE PRICE HAS CHANGED SINCE HE LAST RENEWED":"تغيّر السعر منذ تجديده الأخير","He has been paying JOD 55.00. Club is now JOD 58.00. You must tell him before this goes through.":"كان يدفع JOD 55.00. سعر كلب الآن JOD 58.00. عليك إبلاغه قبل تنفيذ هذا.","From 21 August":"من ٢١ آب","He pays now":"يدفع الآن","Or hold his old price for another twelve months if you would rather not lose him this week.":"أو ثبّت سعره القديم اثني عشر شهراً آخر إن كنت تفضّل عدم خسارته هذا الأسبوع.","Renew at JOD 58.00":"جدّد بـ JOD 58.00","Hold his old price":"ثبّت سعره القديم","Freeze this membership":"جمّد هذه العضوية","Billing pauses · access stops · the Club rate is held · end date moves out by the frozen period.":"الفواتير توقف · الدخول يتوقف · سعر كلب محفوظ · تاريخ الانتهاء يتأخر بمقدار فترة التجميد.","He has used 1 of 3 freeze months this year. Two remain.":"استخدم شهراً من ثلاثة للتجميد هذا العام. بقي شهران.","Freeze for one month":"جمّد شهراً واحداً","Choose dates":"اختر التواريخ","Bring Yara back early":"أعد يارا مبكراً","Frozen until 1 October":"مجمّدة حتى ١ تشرين الأول","RESTART ON":"تُستأنف في","Part month, 1–30 Sep":"شهر جزئي · ١–٣٠ أيلول","Then monthly":"ثم شهرياً","Her renewal date returns to the 24th. One freeze month goes back to her allowance.":"يعود تاريخ تجديدها إلى الرابع والعشرين. ويُعاد شهر تجميد إلى رصيدها.","Restart her membership":"استأنف عضويتها","Upgrade to Club+":"ترقية إلى كلب بلس","Club, 11 days remaining":"كلب · ١١ يوماً متبقية","Club+, 11 days":"كلب بلس · ١١ يوماً","Pay today":"يُدفع اليوم","From 1 Sep the monthly becomes JOD 78.00, up from 55.00.":"من ١ أيلول يصبح الشهري JOD 78.00 بعد أن كان 55.00.","Upgrade and charge 8.43":"ارفع الخطة واخصم ٨٫٤٣","Move Dana to Club":"انقل دانا إلى كلب","From Club+ · JOD 78.00":"من كلب بلس · JOD 78.00","WHAT SHE LOSES":"ما تفقده","Access to Abdoun and Sweifieh\nTwo PT sessions a month\nHer three unused PT credits expire 30 days after the change":"الدخول إلى عبدون والصويفية\nحصتا تدريب شخصي شهرياً\nحصصها الثلاث غير المستخدمة تنتهي بعد ٣٠ يوماً من التغيير","From 24 September":"من ٢٤ أيلول","She saves monthly":"توفّر شهرياً","Takes effect at her next renewal, not today — she keeps Club+ for the month she has paid for.":"يسري عند تجديدها القادم لا اليوم — تبقى على كلب بلس للشهر الذي دفعته.","TYPE HER MEMBER ID TO CONFIRM":"اكتب رقم عضويتها للتأكيد","MEMBER ID":"رقم العضو","Move her to Club":"انقلها إلى كلب","Cancel this membership":"ألغِ هذه العضوية","The 12-month commitment runs to March. Cancelling now triggers a two-month fee of JOD 110.00, and access ends on 18 September after the notice period.":"الالتزام لاثني عشر شهراً يمتد إلى آذار. الإلغاء الآن يترتب عليه رسم شهرين بمقدار JOD 110.00، وينتهي الدخول في ١٨ أيلول بعد مدة الإشعار.","Before you cancel":"قبل الإلغاء","He stopped visiting 19 days ago without giving a reason. A freeze costs him nothing and keeps the commitment intact.":"توقّف عن الزيارة قبل ١٩ يوماً دون ذكر سبب. التجميد لا يكلّفه شيئاً ويحفظ الالتزام كما هو.","Offer a freeze instead":"اعرض التجميد بدلاً من ذلك","REASON · REQUIRED":"السبب · مطلوب","Moving away, cost, unhappy, other…":"انتقال، السعر، عدم رضا، أخرى…","Keep it":"أبقِها","Nadi Group · 3 plans":"مجموعة نادي · ٣ خطط","MEMBERS":"الأعضاء","LAST CHANGED":"آخر تغيير","Jan 2026":"كانون الثاني ٢٠٢٦","CLUB WENT UP THIS MONTH":"ارتفع سعر كلب هذا الشهر","See who renews next":"اعرض من يجدّد تالياً","Refund JOD 28.00":"استرد JOD 28.00","Whey 1kg · Ahmad Nabulsi · sold 2 hours ago":"واي بروتين ١ كغ · أحمد النابلسي · بيع قبل ساعتين","Original sale":"البيع الأصلي","Paid by":"دُفع بـ","Goes back to":"يُعاد إلى","the same card":"البطاقة نفسها","Three to five days to appear on his statement. The sale stays on record — this creates a linked credit note, it does not edit history.":"ثلاثة إلى خمسة أيام حتى يظهر في كشفه. البيع يبقى مسجّلاً — هذا ينشئ إشعاراً دائناً مرتبطاً ولا يعدّل التاريخ.","TYPE THE AMOUNT TO CONFIRM":"اكتب المبلغ للتأكيد","TYPE THE AMOUNT":"اكتب المبلغ","The number is the thing being risked, so you type it rather than clicking yes.":"الرقم هو ما يُخاطر به، فتكتبه بدل النقر على «نعم».","REASON":"السبب","Wrong flavour, unopened":"نكهة خطأ · غير مفتوح","UNPAID · 2 DAYS LATE":"غير مدفوعة · متأخرة يومين","DESCRIPTION":"الوصف","WHAT HAS HAPPENED TO THIS INVOICE":"ما جرى لهذه الفاتورة","Issued and charged automatically":"صدرت وخُصمت تلقائياً","Declined · card expired · Visa ···4417":"مرفوضة · البطاقة منتهية · فيزا ···4417","Retry 1 declined · same reason":"المحاولة ١ مرفوضة · السبب نفسه","Retry 2 declined · dunning stopped":"المحاولة ٢ مرفوضة · توقفت المتابعة","Reminder drafted, awaiting approval":"جُهّز التذكير وينتظر الموافقة","Not submitted — e-invoices are sent on payment, not issue":"لم تُرسل — الفواتير الإلكترونية تُرسل عند الدفع لا عند الإصدار","Jordan requires submission of the settled transaction. An unpaid invoice has nothing to report yet, so this state is correct rather than a failure.":"يشترط الأردن إرسال المعاملة المسددة. الفاتورة غير المدفوعة لا شيء فيها للإبلاغ بعد، فهذه الحالة صحيحة لا فاشلة.","There is no edit affordance on this screen at any permission level. Corrections are credit notes with their own number — which is why this timeline can be trusted as an audit trail.":"لا يوجد خيار تعديل في هذه الشاشة عند أي مستوى صلاحية. التصحيحات إشعارات دائنة بأرقامها الخاصة — ولهذا يمكن الوثوق بهذا السجل كأثر تدقيق.","Editable down for a part payment. Anything over 55.00 goes to his wallet — that will be stated before you confirm.":"قابل للتخفيض لدفعة جزئية. وأي مبلغ يزيد على ٥٥٫٠٠ يذهب إلى محفظته — وسيُذكر ذلك قبل التأكيد.","Wallet · 0.00":"المحفظة · ٠٫٠٠","WHAT THIS SETTLES":"ما تسدّده هذه الدفعة","One open invoice, so allocation is unambiguous. With two or more you choose, and the split is shown before you confirm.":"فاتورة واحدة مفتوحة، فالتخصيص واضح. ومع اثنتين أو أكثر تختار أنت، ويُعرض التوزيع قبل التأكيد.","Take JOD 55.00 by card":"استلم JOD 55.00 بالبطاقة","All retries exhausted · no access blocked":"استُنفدت المحاولات · لم يُمنع أي دخول","Send all 6 links":"أرسل الروابط الستة","Card expired · Visa ···4417":"بطاقة منتهية · فيزا ···4417","link ready":"الرابط جاهز","Insufficient funds":"رصيد غير كافٍ","Card expired · frozen member":"بطاقة منتهية · عضوية مجمّدة","review first":"يحتاج مراجعة","Card expired · membership ended":"بطاقة منتهية · انتهت العضوية","Card expired · Visa ···2201":"بطاقة منتهية · فيزا ···2201","The message they receive":"الرسالة التي يستلمونها","Hi Ahmad — your August payment of JOD 55.00 didn't go through because your card expired. You can pay here: veyro.link/p/8k2m. You're still able to train as normal.":"مرحباً أحمد — لم تُنفَّذ دفعة آب بمقدار JOD 55.00 لأن بطاقتك منتهية. يمكنك الدفع من هنا: veyro.link/p/8k2m. ويمكنك التدريب كالمعتاد.","Sent in each member’s chosen language. Two of the six have withdrawn marketing consent — this is a service message, so it still sends, and the distinction is enforced by the system rather than left to the sender.":"تُرسل بلغة كل عضو المختارة. اثنان من الستة سحبا الموافقة التسويقية — وهذه رسالة خدمة فتُرسل، والتمييز يفرضه النظام لا المرسل.","When a payment fails":"عند فشل الدفع","Nadi Group · all clubs":"مجموعة نادي · جميع الفروع","WE TRY AGAIN":"نعيد المحاولة","Twice — the next morning, then 48 hours later. After that we stop and tell someone.":"مرتين — صباح اليوم التالي، ثم بعد ٤٨ ساعة. بعدها نتوقف ونبلّغ شخصاً.","THEY KEEP TRAINING":"يواصلون التدريب","For 14 days after the first failure. Access is never cut by an automation.":"لمدة ١٤ يوماً بعد أول فشل. ولا تقطع الأتمتة الدخول أبداً.","WE MESSAGE THEM":"نرسل لهم رسالة","A draft is prepared after the second failure. It waits for a person to approve it.":"تُجهَّز مسودة بعد الفشل الثاني. وتنتظر موافقة شخص.","WE NEVER":"لا نفعل أبداً","Cancel a membership, charge a fee, or block entry. Only a person does those.":"إلغاء عضوية أو فرض رسم أو منع دخول. هذه يفعلها شخص فقط.","Written as sentences rather than a rules engine, because an owner has to be able to read this back and recognise their own policy. The NEVER block is not configurable downward.":"مكتوبة كجُمل لا كمحرّك قواعد، لأن على المالك أن يقرأها ويتعرّف على سياسته. وكتلة «لا نفعل أبداً» غير قابلة للتخفيف.","Change the retry schedule":"غيّر جدول إعادة المحاولة","Yoga cancelled 14 Aug":"يوغا ملغاة ١٤ آب","no expiry":"بلا انتهاء","Class credits ×2":"رصيد حصتين","Goodwill · Ziad":"بادرة حسن نية · زياد","This is money owed to members, not revenue. Adding a manual credit is a tier-3 action with your name on it.":"هذا مال مستحق للأعضاء لا إيراد. وإضافة رصيد يدوي إجراء من الدرجة الثالثة يحمل اسمك.","Original":"الأصلي","Sessions used":"الحصص المستخدمة","Already refunded":"المسترد سابقاً","Refundable":"القابل للاسترداد","REFUND":"الاسترداد","Moving abroad, 3 sessions unused":"انتقال للخارج · ٣ حصص غير مستخدمة","Must be more than zero and no more than 84.00. Three credits are removed from his record when this goes through.":"يجب أن يزيد على صفر ولا يتجاوز ٨٤٫٠٠. وتُحذف ثلاث حصص من سجله عند التنفيذ.","Refund JOD 84.00":"استرد JOD 84.00","Khalda · Layla · 16:00–22:00":"خلدا · ليلى · ١٦:٠٠–٢٢:٠٠","Opening float":"الرصيد الافتتاحي","Cash sales":"مبيعات نقدية","Cash refunds":"مستردات نقدية","Should be in the drawer":"المتوقع في الصندوق","COUNTED":"المعدود","Short by":"ناقص بمقدار","Gave change from the wrong note on the 18:40 sale":"أُعطي الباقي من ورقة خطأ في بيع ١٨:٤٠","Anything over JOD 2.00 needs a note. Over JOD 20.00 needs Ziad to countersign.":"أي فرق يزيد على JOD 2.00 يحتاج ملاحظة. وما يزيد على JOD 20.00 يحتاج توقيع زياد.","EVIDENCE DUE 23 AUG":"الأدلة مطلوبة ٢٣ آب","His bank says he did not authorise this. The JOD 45.00 is held by the provider until this is settled — it is not in your account and not lost.":"يقول مصرفه إنه لم يصرّح بهذا. مبلغ JOD 45.00 محتفظ به عند المزوّد حتى تُحل المسألة — ليس في حسابك وليس مفقوداً.","Seven days to respond. No response means the money goes back automatically.":"سبعة أيام للرد. وعدم الرد يعني إعادة المال تلقائياً.","WHAT WE CAN SHOW":"ما يمكننا إظهاره","Signed membership agreement":"اتفاقية عضوية موقّعة","His check-ins during the billing period · 11 visits":"دخولاته في فترة الفاتورة · ١١ زيارة","The receipt sent to his WhatsApp, delivered and read":"الإيصال المرسل لواتسابه · وصل وقُرئ","A record of him disputing this before":"سجل بنزاع سابق منه","Retail":"التجزئة","KHALDA":"خلدا","ABDOUN":"عبدون","Creatine 300g":"كرياتين ٣٠٠ غ","Memberships are tax-exempt in Jordan and appear in a separate group. Price changes need an effective date and state how many members are affected.":"العضويات معفاة من الضريبة في الأردن وتظهر في مجموعة منفصلة. وتغييرات السعر تحتاج تاريخ نفاذ وتوضح عدد الأعضاء المتأثرين.","Khalda · 1 item out, 2 low":"خلدا · صنف غير متوفر واثنان منخفضان","CREATINE HAS BEEN OUT FOR 4 DAYS":"الكرياتين غير متوفر منذ ٤ أيام","It is greyed out at the till rather than hidden, so staff can tell a member it is coming rather than that it does not exist. Nine were sold the week before it ran out.":"يظهر باهتاً في الصندوق لا مخفياً، ليقول الموظف للعضو إنه قادم لا إنه غير موجود. بيع منه تسعة في الأسبوع قبل نفاده.","STAFF":"الموظفون","CORPORATE · ARAMEX":"شركات · أرامكس","OPEN DAY · EXPIRED 12 AUG":"يوم مفتوح · انتهى ١٢ آب","Was 20% off the first month. No longer available.":"كان خصم ٢٠٪ على الشهر الأول. لم يعد متاحاً.","ANYTHING ELSE":"ما عدا ذلك","Up to 10% at a manager’s discretion. Above 10% needs Rania.":"حتى ١٠٪ بتقدير المدير. وما يزيد يحتاج موافقة رانيا.","The 10% threshold is what makes the till ask for a manager. Change it here and every POS terminal follows immediately.":"حد الـ١٠٪ هو ما يجعل الصندوق يطلب مديراً. غيّره هنا وتتبعه كل نقاط البيع فوراً.","Schedule":"الجدول","Mon":"اثن","Tue":"ثلا","Wed":"أرب","Thu":"خمي","Fri":"جمع","Sat":"سبت","Sun":"أحد","Pilates":"بيلاتس","no coach":"بلا مدرب","Only the one class needing a coach carries colour. Fifty-four healthy cells competing for attention would bury it — that was a P1 finding in the Phase 9 audit.":"الحصة الوحيدة التي تحتاج مدرباً هي التي تحمل لوناً. أربع وخمسون خانة سليمة تتنافس على الانتباه كانت ستطمرها — وهذا ما رصدته مراجعة المرحلة التاسعة كخلل من الدرجة الأولى.","Spin · Thursday 19:00":"سبينينغ · الخميس ١٩:٠٠","Studio 2 · 20 bikes · Khalda":"الاستوديو ٢ · ٢٠ دراجة · خلدا","of 20 bikes":"من ٢٠ دراجة","still bookable":"ما زال الحجز متاحاً","WAITLIST":"قائمة الانتظار","auto-promote on":"الترقية التلقائية مفعّلة","USUAL FILL":"الامتلاء المعتاد","Thursday spin":"سبينينغ الخميس","BOOKED · 18":"محجوزة · ١٨","booked 6d ago":"حجزت قبل ٦ أيام","booked 2d ago":"حجزت قبل يومين","booked yesterday":"حجز أمس","trial member":"عضو تجريبي","Show 13 more":"إظهار ١٣ آخرين","Assign Dana":"أسندها لدانا","Message the 18":"راسل الـ١٨","Cancel class":"ألغِ الحصة","Edit Thursday spin":"عدّل سبينينغ الخميس","CLASS":"الحصة","COACH":"المدرب","Unassigned":"غير مُسند","Studio 2 · 20 bikes":"الاستوديو ٢ · ٢٠ دراجة","REPEATS":"التكرار","Every Thursday":"كل خميس","Changing the time or room notifies all eighteen. Changing the coach does not — members book the class, not the person, unless it is a PT slot.":"تغيير الوقت أو القاعة يُبلّغ الثمانية عشر جميعاً. تغيير المدرب لا — فالأعضاء يحجزون الحصة لا الشخص، إلا في حصص التدريب الشخصي.","Khalda · 9 sessions booked this week":"خلدا · ٩ حصص محجوزة هذا الأسبوع","Monday":"الإثنين","Tuesday":"الثلاثاء","Wednesday":"الأربعاء","Thursday":"الخميس","Friday":"الجمعة","Saturday":"السبت","Sunday":"الأحد","Not working":"لا يعمل","Spin 19:00 added":"أُضيفت سبينينغ ١٩:٠٠","The Thursday spin sits outside his stated hours. It was offered and he accepted, so it stands — but it is flagged rather than silently absorbed.":"سبينينغ الخميس خارج ساعاته المعلنة. عُرضت عليه وقبلها فتبقى — لكنها مُعلَّمة لا مُستوعبة بصمت.","Wednesday 26 August, 09:45":"الأربعاء ٢٦ آب · ٠٩:٤٥","Credits he has":"حصصه المتبقية","This session uses":"تستخدم هذه الحصة","Left afterwards":"المتبقي بعدها","His credits expire in November. With none left this screen offers to sell a package rather than refusing.":"حصصه تنتهي في تشرين الثاني. وعند نفادها تعرض هذه الشاشة بيع باقة بدل الرفض.","Khalda · 4 spaces":"خلدا · ٤ مساحات","Studio 1":"الاستوديو ١","Mats, mirrors":"حصائر ومرايا","Studio 2":"الاستوديو ٢","Main floor":"الصالة الرئيسية","Free weights, machines":"أوزان حرة وأجهزة","open":"مفتوحة","PT room":"غرفة التدريب الشخصي","Platform, rack":"منصة وحمّالة","Capacity here is what stops a class being overbooked and what makes double-booking impossible when a class is created. It is a constraint, not a label.":"السعة هنا هي ما يمنع تجاوز حجوزات الحصة ويجعل الحجز المزدوج مستحيلاً عند إنشائها. قيد لا وصف.","YOU MUST TELL THEM SOMETHING":"عليك إبلاغهم بشيء","This cannot go through without a message and a choice for each member. A class that vanishes silently is the most damaging thing this screen could allow.":"لا يُنفَّذ هذا دون رسالة وخيار لكل عضو. حصة تختفي بصمت أكثر ما يمكن لهذه الشاشة أن تسمح به ضرراً.","No coach available — our mistake, sorry":"لا يوجد مدرب متاح — خطؤنا، نعتذر","Friday 19:00 instead":"الجمعة ١٩:٠٠ بدلاً منها","Friday has 6 free bikes, so 12 of the 18 would need the credit anyway. Sent in each member’s own language.":"الجمعة فيها ٦ دراجات متاحة، فـ١٢ من الـ١٨ سيحتاجون الرصيد على أي حال. تُرسل بلغة كل عضو.","Cancel and notify all 18":"ألغِ وأبلغ الـ١٨","One device down · 3 clubs":"جهاز واحد متعطل · ٣ فروع","across 3 clubs":"في الفروع الثلاثة","responding":"تستجيب","Khalda · turnstile 1":"خلدا · البوابة ١","Working":"تعمل","Khalda · turnstile 2":"خلدا · البوابة ٢","Sweifieh · turnstile 1":"الصويفية · البوابة ١","Not responding":"لا تستجيب","since 09:04":"منذ ٠٩:٠٤","Sweifieh · turnstile 2":"الصويفية · البوابة ٢","Abdoun · turnstile 1":"عبدون · البوابة ١","Sweifieh turnstile 1 has been down for 16 minutes. Members are entering through turnstile 2 and the desk, and every entry is recorded. Nothing is lost — this is a queue at the door, not a data problem.":"بوابة الصويفية ١ متعطلة منذ ١٦ دقيقة. يدخل الأعضاء من البوابة ٢ ومن الاستقبال، وكل دخول يُسجّل. لا شيء يُفقد — هذا صف على الباب لا مشكلة بيانات.","MEMBERSHIP ENDED":"انتهت العضوية","DEVICE DOWN":"عطل جهاز","NO CREDENTIAL":"بلا وسيلة دخول","Four of these were the Sweifieh fault, not policy — they should be apologised to. Filtering by reason is what separates \"our equipment failed\" from \"their membership ended\".":"أربعة منها بسبب عطل الصويفية لا بسبب السياسة — ويستحقون اعتذاراً. التصفية بالسبب هي ما يفصل «تعطّل جهازنا» عن «انتهت عضويتهم».","Card, app and fingerprint":"بطاقة وتطبيق وبصمة","Card ···8841":"بطاقة ···8841","Active since March 2024":"نشطة منذ آذار ٢٠٢٤","Replace":"استبدل","Active · rotates every 30 seconds":"نشط · يتغير كل ٣٠ ثانية","Revoke":"إلغاء","Fingerprint":"البصمة","Enrolled 4 March 2024":"سُجّلت ٤ آذار ٢٠٢٤","Remove":"حذف","WHAT WE HOLD, AND WHAT WE DO NOT":"ما نحفظه وما لا نحفظه","Only whether a fingerprint is enrolled. Not an image, not a template, not anything exportable. It cannot be viewed on this screen or any other, by any role.":"فقط ما إذا كانت البصمة مسجّلة. لا صورة ولا قالب ولا أي شيء قابل للتصدير. ولا يمكن عرضها في هذه الشاشة ولا غيرها لأي دور.","Removing it needs Rania’s approval and is logged where Ahmad can see it.":"حذفها يتطلب موافقة رانيا ويُسجّل حيث يستطيع أحمد رؤيته.","Reception":"الاستقبال","Owner":"المالك","All 3":"الفروع الثلاثة","now":"الآن","Club manager":"مدير الفرع","Accountant":"المحاسب","Coach":"مدرب","yesterday":"أمس","Khalda, Abdoun":"خلدا وعبدون","Reception · Khalda · joined June 2024":"الاستقبال · خلدا · انضمت حزيران ٢٠٢٤","WHAT SHE CAN DO":"ما تستطيع فعله","Check members in and out\nTake payments and sell retail\nBook classes and PT\nSee membership and payment state":"تسجيل دخول الأعضاء وخروجهم\nاستلام المدفوعات وبيع التجزئة\nحجز الحصص والتدريب الشخصي\nرؤية حالة العضوية والدفع","EXTRA PERMISSIONS · GRANTED ONE BY ONE":"صلاحيات إضافية · تُمنح واحدة واحدة","Approve refunds":"الموافقة على المستردات","Export member data":"تصدير بيانات الأعضاء","Owner only at this club":"المالك فقط في هذا الفرع","See health notes":"رؤية الملاحظات الصحية","Coaches and nutritionists":"المدربون وأخصائيو التغذية","Override a denied entry":"تجاوز منع الدخول","Granted by Ziad, 4 July":"منحها زياد في ٤ تموز","Changing a permission is a tier-4 action and needs Rania. You cannot grant a permission you do not hold yourself — Ziad cannot give Layla export rights he does not have.":"تغيير الصلاحية إجراء من الدرجة الرابعة ويحتاج رانيا. ولا يمكنك منح صلاحية لا تملكها — لا يستطيع زياد منح ليلى حق تصدير لا يملكه.","Khalda only":"خلدا فقط","INVITATION EXPIRES":"تنتهي الدعوة","In 7 days":"بعد ٧ أيام","She sets her own password and two-factor on first sign-in. Nobody, including you, can see it.":"تضع كلمة سرها والتحقق الثنائي عند أول دخول. ولا يستطيع أحد، ولا أنت، رؤيتها.","OWNER":"المالك","RECEP":"استقبال","SALES":"مبيعات","See member records":"رؤية سجلات الأعضاء","Take payments":"استلام المدفوعات","Change memberships":"تغيير العضويات","Export data":"تصدير البيانات","Change permissions":"تغيير الصلاحيات","Changing permissions and starting an impersonation are Owner-only and cannot be delegated, whatever a tenant configures here.":"تغيير الصلاحيات وبدء انتحال الهوية للمالك وحده ولا يمكن تفويضهما، أياً كان ما يضبطه المستأجر هنا.","WhatsApp · 079 555 0134":"واتساب · 079 555 0134","Marketing consent withdrawn 12 July. Service messages about payments, bookings and access are still permitted. Promotional templates do not appear below.":"سُحبت الموافقة التسويقية في ١٢ تموز. رسائل الخدمة عن المدفوعات والحجوزات والدخول لا تزال مسموحة. والقوالب الترويجية لا تظهر أدناه.","Hi, is the 19:00 spin on Thursday still running?":"مرحباً، هل حصة السبينينغ ١٩:٠٠ الخميس ما زالت قائمة؟","Yes — we're confirming the coach today and I'll message you by this evening.":"نعم — نؤكد المدرب اليوم وسأراسلك مساء اليوم.","Great, thanks":"ممتاز، شكراً","Payment link":"رابط دفع","Class confirmed":"تأكيد حصة","Renewal due":"تجديد مستحق","Outside the 24-hour window only approved templates can open a conversation. Free text is disabled and the reason is stated rather than the Send button silently failing.":"خارج نافذة الـ٢٤ ساعة لا تفتح المحادثة إلا القوالب المعتمدة. الكتابة الحرة معطّلة والسبب مذكور بدل أن يفشل زر الإرسال بصمت.","Service":"خدمة","Approved":"معتمد","Class cancelled":"إلغاء حصة","Renewal reminder":"تذكير بالتجديد","Open day invitation":"دعوة يوم مفتوح","Marketing":"تسويق","Refer a friend":"رشّح صديقاً","Waiting on WhatsApp":"بانتظار واتساب","WHY APPROVAL IS NOT OURS TO GIVE":"لماذا الموافقة ليست بيدنا","WhatsApp approves templates, not Veyro. \"Refer a friend\" has been pending with them for four days. We show their real state rather than pretending it is ready.":"واتساب هو من يعتمد القوالب لا Veyro. قالب «رشّح صديقاً» معلّق عندهم منذ أربعة أيام. نعرض حالته الحقيقية بدل التظاهر بأنه جاهز.","Not visited in 30 days · 214 members":"لم يزوروا منذ ٣٠ يوماً · ٢١٤ عضواً","Will actually receive it":"من سيستلمها فعلاً","WHAT THEY GET":"ما يستلمونه","We haven't seen you at Khalda for a while. Your membership is still active — come in whenever you like, or reply here if something has changed.":"لم نرك في خلدا منذ فترة. عضويتك ما زالت نشطة — تعال وقتما تشاء، أو ردّ هنا إن تغيّر شيء.","Sent in each member’s own language. 121 will receive Arabic, 65 English.":"تُرسل بلغة كل عضو. ١٢١ سيستلمونها بالعربية و٦٥ بالإنجليزية.","Send to 186 members":"أرسل إلى ١٨٦ عضواً","MANAGER":"المدير","ACCOUNTANT":"المحاسب","A payment fails":"فشل دفعة","A membership expires soon":"عضوية تقارب الانتهاء","A class has no coach":"حصة بلا مدرب","A device stops responding":"جهاز يتوقف عن الاستجابة","A lead goes 48h without contact":"عميل محتمل بلا تواصل ٤٨ ساعة","A refund is requested":"طلب استرداد","Defaults are deliberately quiet. Nothing opts anyone into a channel they did not choose, and an owner cannot subscribe staff to alerts on their behalf.":"الإعدادات الافتراضية هادئة بقصد. لا شيء يُدخل أحداً في قناة لم يخترها، ولا يستطيع المالك تسجيل موظفيه في تنبيهات بالنيابة عنهم.","Call the 5 members who have not visited in 20 days":"اتصل بالأعضاء الخمسة الذين لم يزوروا منذ ٢٠ يوماً","Retention item · Ziad":"بند استمرارية · زياد","Verify 22 PT sessions":"وثّق ٢٢ حصة تدريب","Coach queue · Yousef":"قائمة المدرب · يوسف","Fix 3 JoFotara invoices":"صحّح ٣ فواتير جوفوترة","Compliance · Nadia":"امتثال · نادية","Order creatine":"اطلب كرياتين","Low stock · Ziad":"مخزون منخفض · زياد","Tomorrow":"غداً","Renew Layla’s first aid certificate":"جدّد شهادة الإسعافات لليلى","Document expiry · Ziad":"انتهاء وثيقة · زياد","Three of these were created by Veyro from attention items and link back to them. Two were typed by a person.":"ثلاثة منها أنشأها Veyro من بنود الانتباه وترتبط بها. واثنان كتبهما شخص.","Failed payment follow-up":"متابعة الدفعات الفاشلة","Active":"نشطة","Renewal reminder, 7 days out":"تذكير بالتجديد قبل ٧ أيام","Welcome a new member":"ترحيب بعضو جديد","Win back after 30 days away":"استعادة بعد ٣٠ يوماً من الغياب","WHY THE WIN-BACK IS PAUSED":"لماذا أُوقفت قاعدة الاستعادة","Active since March · 412 runs":"نشطة منذ آذار · ٤١٢ تنفيذاً","A payment fails for any reason.":"فشل دفعة لأي سبب.","The next morning, then 48 hours later. Twice, then we stop.":"صباح اليوم التالي، ثم بعد ٤٨ ساعة. مرتان ثم نتوقف.","AFTER THE SECOND FAILURE":"بعد الفشل الثاني","A message is drafted naming the amount and the reason, with a payment link. It waits for someone to approve it.":"تُجهَّز رسالة تذكر المبلغ والسبب مع رابط دفع. وتنتظر موافقة شخص.","For 14 days. Access is never cut by this rule.":"لمدة ١٤ يوماً. ولا تقطع هذه القاعدة الدخول أبداً.","Cancel a membership, add a fee, or block entry. A person does those or nobody does.":"إلغاء عضوية أو إضافة رسم أو منع دخول. يفعلها شخص أو لا تُفعل.","WHAT IT HAS DONE":"ما أنجزته","See every run":"اعرض كل تنفيذ","Pause it":"أوقفها","Failed payment follow-up · runs":"متابعة الدفعات الفاشلة · التنفيذات","Last 48 hours":"آخر ٤٨ ساعة","Retry 2 declined · message drafted":"المحاولة ٢ مرفوضة · جُهّزت رسالة","Retry 1 succeeded":"نجحت المحاولة ١","Link opened, paid":"فُتح الرابط ودُفع","This is how a manager audits something they cannot watch happening. Two drafts are waiting — the automation stops short of sending on its own, by design.":"هكذا يدقّق المدير على ما لا يستطيع مشاهدته يحدث. مسودتان تنتظران — والأتمتة تتوقف قبل الإرسال من تلقاء نفسها، بقصد.","Five available to you":"خمسة متاحة لك","What came in, by club and plan":"ما دخل، حسب الفرع والخطة","Who joined, who left, who stayed":"من انضم ومن ترك ومن بقي","When the gym is busy":"متى يزدحم النادي","Sessions delivered and verified":"الحصص المنفّذة والموثّقة","What sells and what sits":"ما يُباع وما يبقى","August to date":"من بداية آب","now 4,812":"الآن ٤٨١٢","STAYED A YEAR":"بقوا سنة","of last August’s joiners":"من منضمي آب الماضي","Moved away":"انتقل","Not using it":"لا يستخدمها","Unhappy":"غير راضٍ","No reason given":"دون ذكر سبب","Six left over price in the month Club went up by JOD 3.00. Worth watching next month before drawing a conclusion from one data point.":"ستة تركوا بسبب السعر في الشهر الذي ارتفعت فيه كلب بمقدار JOD 3.00. يستحق المتابعة الشهر القادم قبل الاستنتاج من نقطة واحدة.","Khalda · last 30 days":"خلدا · آخر ٣٠ يوماً","Export revenue data":"صدّر بيانات الإيرادات","August · all clubs":"آب · جميع الفروع","THIS CONTAINS PERSONAL AND FINANCIAL DATA":"يحتوي هذا بيانات شخصية ومالية","WHY DO YOU NEED IT":"لماذا تحتاجه","Quarterly review with the accountant":"مراجعة ربعية مع المحاسب","Your name, the reason and the time are recorded in the audit log, which Rania can read.":"اسمك والسبب والوقت تُسجّل في سجل التدقيق الذي تستطيع رانيا قراءته.","LEGAL NAME":"الاسم القانوني","Nadi Group for Sports Services LLC":"مجموعة نادي للخدمات الرياضية ذ.م.م","TRADING NAME":"الاسم التجاري","REGISTERED ADDRESS":"العنوان المسجّل","Abdoun Circle, Amman 11183, Jordan":"دوار عبدون · عمّان ١١١٨٣ · الأردن","TAX NUMBER":"الرقم الضريبي","CONTACT":"جهة الاتصال","The legal name and tax number appear on every invoice and every JoFotara submission. Changing them changes documents already issued going forward, not retrospectively.":"الاسم القانوني والرقم الضريبي يظهران في كل فاتورة وكل إرسال لجوفوترة. وتغييرهما يسري على ما يصدر لاحقاً لا بأثر رجعي.","One of three clubs":"أحد ثلاثة فروع","ADDRESS":"العنوان","Khalda, Amman":"خلدا · عمّان","OPENING HOURS":"ساعات العمل","Sat–Thu 06:00–23:00 · Fri 08:00–22:00":"السبت–الخميس ٠٦:٠٠–٢٣:٠٠ · الجمعة ٠٨:٠٠–٢٢:٠٠","FLOOR CAPACITY":"سعة الصالة","Friday hours differ because of prayers — the schedule and the booking engine both read this rather than assuming a Monday-to-Sunday week.":"ساعات الجمعة مختلفة بسبب الصلاة — والجدول ومحرّك الحجز يقرآن هذا بدل افتراض أسبوع من الإثنين إلى الأحد.","Nadi Group · Jordan · JOD":"مجموعة نادي · الأردن · JOD","SALES TAX":"ضريبة المبيعات","JoFotara e-invoicing":"الفوترة الإلكترونية جوفوترة","Submitting since 14 June. 1,847 invoices sent, 3 rejected this month — all three for a missing buyer tax number, all corrected and resubmitted.":"الإرسال منذ ١٤ حزيران. ١٨٤٧ فاتورة أُرسلت، و٣ مرفوضة هذا الشهر — الثلاث لنقص الرقم الضريبي للمشتري، وصُحّحت وأُعيد إرسالها.","Test the connection":"اختبر الاتصال","Submission log":"سجل الإرسال","A business sale needs the buyer’s tax number. The till now requires it at the point of sale rather than failing later at submission — which is what caused this month’s three rejections.":"البيع للشركات يحتاج الرقم الضريبي للمشتري. والصندوق يطلبه الآن عند البيع بدل الفشل لاحقاً عند الإرسال — وهو ما سبّب رفض هذا الشهر الثلاثة.","This screen is the same shape everywhere. A UK tenant sees HMRC here instead, with different fields — nothing about it is hard-coded to Jordan except the adapter.":"هذه الشاشة بالشكل نفسه في كل مكان. المستأجر البريطاني يرى هيئة الضرائب البريطانية هنا بحقول مختلفة — ولا شيء فيها مرتبط بالأردن إلا المحوّل.","How money comes in":"كيف يدخل المال","Nadi Group · Jordan":"مجموعة نادي · الأردن","Card payments":"مدفوعات البطاقات","Connected · Network International":"متصل · نتورك إنترناشونال","Last settled this morning":"آخر تسوية هذا الصباح","Connected · Arab Bank":"متصل · البنك العربي","Instant transfers from member phones":"تحويلات فورية من هواتف الأعضاء","Enabled at all 3 clubs":"مفعّل في الفروع الثلاثة","Reconciled per shift":"يُجرَد كل وردية","WHEN THE CARD READER CANNOT BE REACHED":"عند تعذّر الوصول لقارئ البطاقات","Sales queue locally and submit when the connection returns. The receipt says \"payment pending\" rather than \"paid\" — telling a member they have paid before the bank confirms is the one error this must never make.":"المبيعات تُدرَج محلياً وتُرسل عند عودة الاتصال. والإيصال يقول «الدفعة معلّقة» لا «مدفوعة» — فإخبار العضو بأنه دفع قبل تأكيد المصرف هو الخطأ الوحيد الذي لا يجوز وقوعه.","Cash and CliQ are unaffected and keep working.":"النقد وكليك غير متأثرين ويعملان.","e-invoicing · Jordan":"الفوترة الإلكترونية · الأردن","Submitting since June":"الإرسال منذ حزيران","WhatsApp Business":"واتساب للأعمال","Member messaging":"مراسلة الأعضاء","Healthy":"سليم","CliQ · Arab Bank":"كليك · البنك العربي","Bank transfers":"التحويلات المصرفية","Access hardware":"أجهزة الدخول","Disconnecting anything here states what stops working first. Removing WhatsApp, for example, stops payment links and class notifications — not just messaging.":"فصل أي خدمة هنا يوضّح ما يتوقف أولاً. إزالة واتساب مثلاً توقف روابط الدفع وتنبيهات الحصص — لا المراسلة وحدها.","YOUR COLOUR":"لونك","Passes · 10.13:1 on white, clearly different from every status colour":"مقبول · ١٠٫١٣:١ على الأبيض، ومختلف بوضوح عن كل ألوان الحالات","WHAT YOUR COLOUR CANNOT BECOME":"ما لا يمكن أن يصبح لونك","It cannot be used for paid, failed, overdue or frozen, and it cannot be the colour of Veyro’s AI. If you pick a green close to the one we use for confirmed payments, we will say so and offer the nearest shade that works.":"لا يُستخدم للمدفوع أو الفاشل أو المتأخر أو المجمّد، ولا يكون لون تحليلات Veyro. وإن اخترت أخضر قريباً من لون المدفوعات المؤكدة سنخبرك ونعرض أقرب درجة صالحة.","A member misreading a failed payment as paid is worse than a brand being slightly off.":"أن يقرأ عضو دفعة فاشلة كمدفوعة أسوأ من أن تكون الهوية بعيدة قليلاً.","Full colour and a single-colour version. The second one is required — it is what appears on receipts, invoices and printed exports.":"نسخة ملونة ونسخة بلون واحد. والثانية مطلوبة — فهي ما يظهر على الإيصالات والفواتير والمطبوعات.","LANGUAGES OFFERED":"اللغات المتاحة","Arabic and English":"العربية والإنجليزية","DEFAULT FOR NEW MEMBERS":"الافتراضية للأعضاء الجدد","Arabic":"العربية","NUMERALS":"الأرقام","Latin digits with JOD · JOD 55.00":"أرقام لاتينية مع JOD · JOD 55.00","DATES":"التواريخ","WEEK STARTS":"يبدأ الأسبوع","Money keeps Latin digits even in Arabic, because that is the form on your invoices and JoFotara submissions. A member disputing a charge must see the same string in both places.":"المال يحفظ الأرقام اللاتينية حتى بالعربية، لأن هذه صورته في فواتيرك وإرسالات جوفوترة. والعضو الذي ينازع مبلغاً يجب أن يرى النص نفسه في الموضعين.","Nadi Group · 24 staff accounts":"مجموعة نادي · ٢٤ حساب موظف","TWO-FACTOR":"التحقق الثنائي","Required for everyone":"مطلوب للجميع","SIGNED OUT AFTER":"الخروج التلقائي بعد","RE-CONFIRM PASSWORD BEFORE":"تأكيد كلمة السر قبل","Refunds, exports, permission changes":"المستردات والتصدير وتغيير الصلاحيات","Veyro support opened your data":"فتح دعم Veyro بياناتك","Read only · ticket #4182 · 21 minutes":"قراءة فقط · تذكرة #4182 · ٢١ دقيقة","By Rania":"بواسطة رانيا","You can read every time Veyro staff opened your data, why, and for how long. That entry is written by us and cannot be removed by us.":"يمكنك قراءة كل مرة فتح فيها موظفو Veyro بياناتك، ولماذا، ولكم من الوقت. نحن نكتب هذا السجل ولا نستطيع حذفه.","PT revenue at Khalda is down JOD 1,840":"إيرادات التدريب الشخصي في خلدا أقل بمقدار JOD 1,840","PT session records, 1–19 August, Khalda · 214 rows\nOmar Sabri’s roster and hours, July and August\nPT invoices for the same period · 96 rows":"سجلات حصص التدريب · ١–١٩ آب · خلدا · ٢١٤ صفاً\nقائمة عمر صبري وساعاته · تموز وآب\nفواتير التدريب للفترة نفسها · ٩٦ صفاً","WHERE WE ARE CONFIDENT, AND WHERE NOT":"حيث نثق وحيث لا نثق","The 31 unverified sessions and the JOD 1,240 are arithmetic from records — certain. That the roster change caused the drop is an inference, and a weaker one: his remaining clients also booked less, which the roster change does not explain.":"الحصص الـ٣١ غير الموثّقة ومبلغ JOD 1,240 حساب مباشر من السجلات — مؤكد. أما أن تغيير القائمة سبّب التراجع فهو استنتاج، وأضعف: فعملاؤه الباقون حجزوا أقل أيضاً، وهذا لا يفسّره تغيير القائمة.","ahmad":"أحمد","Club · Khalda · owes JOD 55.00":"كلب · خلدا · عليه JOD 55.00","Flex · Khalda":"فليكس · خلدا","ACTIONS":"الإجراءات","from any member record":"من أي سجل عضو","walk-in join":"انضمام مباشر","SCREENS":"الشاشات","the ledger":"الدفتر","Failed payment recovery":"استرداد الدفعات الفاشلة","ASK VEYRO":"اسأل Veyro","reads payments, sessions and rosters":"يقرأ المدفوعات والحصص وقوائم المدربين","Only things you can actually open. Nadia searching the same word sees invoices; Layla sees no export action at all.":"ما تستطيع فتحه فعلاً فقط. نادية تبحث الكلمة نفسها فترى فواتير؛ وليلى لا ترى إجراء تصدير على الإطلاق.","PASSWORD":"كلمة السر","A code from your phone comes next. If the email or password is wrong we say so without telling you which — that is deliberate.":"يأتي بعدها رمز من هاتفك. وإن كان البريد أو كلمة السر خطأ نقول ذلك دون تحديد أيهما — وهذا مقصود.","CONFIRM IT IS YOU":"أكّد أنك أنت","Refunding JOD 84.00":"استرداد JOD 84.00","You signed in four hours ago. Anything that moves money needs your password again — it takes a second and it means a borrowed screen cannot issue refunds.":"سجّلت الدخول قبل أربع ساعات. وأي إجراء يحرّك مالاً يحتاج كلمة سرك مرة أخرى — يستغرق ثانية ويعني أن شاشة مستعارة لا تستطيع إصدار مستردات.","Cancelling returns you to the refund, not to the beginning.":"الإلغاء يعيدك إلى الاسترداد لا إلى البداية.","Nothing scanned — search instead":"لم يُمسح شيء — ابحث بدلاً من ذلك","NAME, PHONE OR MEMBER ID":"الاسم أو الهاتف أو رقم العضوية","ahmad n":"أحمد ن","Club · Khalda":"كلب · خلدا","Ahmed Nabhan":"أحمد نبهان","Club+ · Abdoun":"كلب بلس · عبدون","Other club":"فرع آخر","Photos are shown so you confirm the person in front of you, not just the name. Three Ahmads is normal at this size.":"تُعرض الصور لتتأكد من الشخص أمامك لا من الاسم وحده. ثلاثة باسم أحمد أمر معتاد بهذا الحجم.","Turnstile 2 · 18:39 · membership ended 7 August":"البوابة ٢ · ١٨:٣٩ · انتهت العضوية ٧ آب","His membership ended twelve days ago and the grace period ran out five days ago. He was here three times a week for two years.":"انتهت عضويته قبل اثني عشر يوماً وانتهت المهلة قبل خمسة أيام. كان يأتي ثلاث مرات أسبوعياً لعامين.","You can let him in — it records who authorised it and why.":"يمكنك السماح له بالدخول — ويُسجّل من صرّح بذلك ولماذا.","Let him in and flag it":"اسمح له بالدخول وسجّل الحالة","Day pass · JOD 8.00":"تصريح يومي · JOD 8.00","Version 4, June 2026. She reads and accepts it on the tablet — the version she accepted is stored with her record.":"الإصدار ٤ · حزيران ٢٠٢٦. تقرأه وتقبله على الجهاز — والإصدار الذي قبلته يُحفظ مع سجلها.","Take payment · JOD 8.00":"استلم الدفعة · JOD 8.00","Seven days, free":"سبعة أيام مجاناً","Two things and she can train today. Everything else the sales team collects later.":"أمران ويمكنها التدريب اليوم. وكل ما عداهما يجمعه فريق المبيعات لاحقاً.","This creates her real member record. When she joins, nothing is typed again — the trial becomes the membership.":"هذا ينشئ سجل عضويتها الحقيقي. وعند انضمامها لا يُكتب شيء من جديد — التجربة تصبح العضوية.","Spin · 19:00":"سبينينغ · ١٩:٠٠","Studio 2 · 18 booked · 12 arrived":"الاستوديو ٢ · ١٨ محجوزة · وصل ١٢","Arrived 18:41":"وصلت ١٨:٤١","Arrived 18:44":"وصلت ١٨:٤٤","Not here yet":"لم يحضر بعد","Waitlist · promoted":"قائمة انتظار · تمت الترقية","Bikes are released at 18:55. Faris came off the waitlist when Nour cancelled.":"تُحرَّر الدراجات ١٨:٥٥. صعد فارس من قائمة الانتظار عند إلغاء نور.","Cash taken":"النقد المستلم","Cash expected":"النقد المتوقع","WHAT YOU COUNTED":"ما عددته","Matches. No note needed.":"مطابق. لا حاجة لملاحظة.","One thing needs attention":"أمر واحد يحتاج انتباهاً","Card reader":"قارئ البطاقات","Connected":"متصل","Receipt printer":"طابعة الإيصالات","Turnstile 1":"البوابة ١","Turnstile 2":"البوابة ٢","Barcode scanner":"ماسح الباركود","Turnstile 2 stopped responding at 09:04. Members can still come in through turnstile 1 or check in here at the desk — nothing is lost.":"توقفت البوابة ٢ عن الاستجابة ٠٩:٠٤. يستطيع الأعضاء الدخول من البوابة ١ أو التسجيل هنا في الاستقبال — ولا شيء يُفقد.","No connection · you can keep working":"لا اتصال · يمكنك مواصلة العمل","Check-in works from what's already on this machine. Cash and CliQ sales record normally. Card sales queue and go through when the connection returns.":"التسجيل يعمل من البيانات الموجودة على هذا الجهاز. مبيعات النقد وكليك تُسجّل عادياً. ومبيعات البطاقات تُدرَج وتُنفَّذ عند عودة الاتصال.","Offline 6 minutes · 2 sales queued · retrying":"بلا اتصال ٦ دقائق · مبيعتان مُدرَجتان · إعادة المحاولة","Khalda · front desk":"خلدا · الاستقبال","Wednesday 18:47":"الأربعاء ١٨:٤٧","Member check-in · from cached records\nCash and CliQ sales\nClass rosters for today":"تسجيل دخول الأعضاء · من السجلات المحفوظة\nمبيعات النقد وكليك\nقوائم حصص اليوم","WHAT DOESN'T":"ما لا يعمل","Card payments · queued, not taken\nNew memberships\nAnything about other clubs":"مدفوعات البطاقات · مُدرَجة لا مستلمة\nالعضويات الجديدة\nأي شيء عن الفروع الأخرى","Card terminal":"جهاز البطاقات","WAITING FOR THE CARD":"بانتظار البطاقة","Terminal is ready. Tap, insert or swipe.":"الجهاز جاهز. المس أو أدخل أو اسحب.","Simulate approval":"محاكاة الموافقة","Simulate decline":"محاكاة الرفض","Simulate offline":"محاكاة انقطاع الاتصال","No timeout is shown to the member — a countdown makes people fumble.":"لا يُعرض عدّاد للعضو — التنازلي يجعل الناس يتلخبطون.","Split payment":"دفع مقسّم","Total due":"المجموع المستحق","Still to collect":"المتبقي للتحصيل","The running remainder is always the largest number on screen after the total. A split that ends 50 fils short is the most common cash-drawer discrepancy there is.":"المتبقي الجاري هو أكبر رقم على الشاشة بعد المجموع دائماً. والدفع المقسّم الذي ينقصه ٥٠ فلساً أشهر فرق في صندوق النقد.","Wallet · 12.50":"المحفظة · ١٢٫٥٠","Cash · 20.00":"نقداً · ٢٠٫٠٠","Card · 60.72":"بطاقة · ٦٠٫٧٢","Monthly rolling. He can stop any time with 30 days notice — no commitment fee.":"شهرية متجددة. يمكنه التوقف في أي وقت بإشعار ٣٠ يوماً — بلا رسم التزام.","Take payment · JOD 40.00":"استلم الدفعة · JOD 40.00","Use within 3 months":"تُستخدم خلال ٣ أشهر","Use within 6 months · best value":"تُستخدم خلال ٦ أشهر · أفضل قيمة","Use within 12 months":"تُستخدم خلال ١٢ شهراً","Credits appear on Ahmad’s record straight away and Yousef sees them.":"تظهر الحصص في سجل أحمد فوراً ويراها يوسف.","Take payment · JOD 280.00":"استلم الدفعة · JOD 280.00","Whey 1kg · sold 2 hours ago":"واي بروتين ١ كغ · بيع قبل ساعتين","This goes back to the same card. It usually takes three to five days to appear.":"يُعاد إلى البطاقة نفسها. ويستغرق ظهوره عادة ثلاثة إلى خمسة أيام.","Sale 20419 · JOD 60.72":"بيع 20419 · JOD 60.72","Nadi Group · Khalda":"مجموعة نادي · خلدا","Tax no. 1099238471":"الرقم الضريبي 1099238471","Water 500ml × 2":"ماء ٥٠٠ مل × ٢","Sales tax 16% on retail":"ضريبة مبيعات ١٦٪ على التجزئة","Card ···4417 · 19 Aug 18:52\nJoFotara ref JO-2026-0819-4471":"بطاقة ···4417 · ١٩ آب ١٨:٥٢\nمرجع جوفوترة JO-2026-0819-4471","Day 4 of onboarding · Starter · 1 club":"اليوم ٤ من التهيئة · المبتدئة · فرع واحد","Organisation and region":"المؤسسة والمنطقة","Done 4 days ago":"أُنجز قبل ٤ أيام","First administrator invited":"دُعي أول مسؤول","Clubs and opening hours":"الفروع وساعات العمل","Done 3 days ago":"أُنجز قبل ٣ أيام","Done 2 days ago":"أُنجز قبل يومين","Payment provider":"مزوّد الدفع","Not started":"لم يبدأ","Staff accounts":"حسابات الموظفين","They can open the doors before the last three are finished — members can join and pay at the desk without access hardware. The order matters less than not being blocked.":"يمكنهم افتتاح النادي قبل إتمام الثلاثة الأخيرة — فالأعضاء يستطيعون الانضمام والدفع في الاستقبال دون أجهزة دخول. الترتيب أقل أهمية من عدم التعطّل.","Growth · 3 clubs · Amman, Jordan":"النمو · ٣ فروع · عمّان · الأردن","since June 2026":"منذ حزيران ٢٠٢٦","Good":"جيدة","no open incidents":"لا حوادث مفتوحة","current":"الحالي","Counts only. No member names, phone numbers or payment details are on this screen — opening their data needs an impersonation session with a stated reason.":"أعداد فقط. لا أسماء أعضاء ولا أرقام هواتف ولا تفاصيل دفع على هذه الشاشة — وفتح بياناتهم يحتاج جلسة انتحال هوية بسبب معلَن.","ORGANISATION":"المؤسسة","REGION":"المنطقة","Jordan · data stays in-region":"الأردن · البيانات تبقى في المنطقة","Starter · 1 club, 500 members":"المبتدئة · فرع واحد · ٥٠٠ عضو","FIRST ADMINISTRATOR":"أول مسؤول","REGION CANNOT BE CHANGED LATER":"لا يمكن تغيير المنطقة لاحقاً","Region sets where their data lives and which tax adapter they get — JoFotara for Jordan. Moving a tenant afterwards means a migration, not a setting.":"المنطقة تحدد مكان بياناتهم ومحوّل الضرائب — جوفوترة للأردن. ونقل المستأجر بعدها ترحيل لا إعداد.","Create and invite Rana":"أنشئ وادعُ رنا","Pulse Amman · 1,284 rows":"بَلس عمّان · ١٢٨٤ صفاً","clean, already live":"سليمة ومباشرة","need a decision":"تحتاج قراراً","Missing join date":"تاريخ انضمام ناقص","Use their first payment date":"استخدم تاريخ أول دفعة","Apply to all 18":"طبّق على الـ١٨","Duplicate phone number":"رقم هاتف مكرر","Merge into one record":"ادمج في سجل واحد","Apply to all 6":"طبّق على الستة","Unrecognised plan name":"اسم خطة غير معروف","Map to an existing plan":"اربطه بخطة قائمة","Apply to all 3":"طبّق على الثلاثة","The clean 1,257 are already in and usable. These 27 wait rather than blocking the rest.":"الـ١٢٥٧ السليمة مُدخلة وقابلة للاستخدام. وهذه الـ٢٧ تنتظر بدل تعطيل الباقي.","Nadi Group · Growth":"مجموعة نادي · النمو","Clubs":"الفروع","Monthly":"شهرياً","Renews":"يتجدد","Nutrition coaching · on\nAutomations · on\nWhite-label branding · on\nAPI access · off":"التدريب الغذائي · مفعّل\nالأتمتة · مفعّلة\nالهوية البصرية الخاصة · مفعّلة\nواجهة البرمجة · معطّلة","Change their plan":"غيّر خطتهم","Nadi Group · August":"مجموعة نادي · آب","WhatsApp messages this month":"رسائل واتساب هذا الشهر","Storage":"المساحة","Nothing near a limit. When something passes 80% it raises an internal task rather than an unexpected invoice.":"لا شيء قريب من الحد. وعند تجاوز ٨٠٪ يُنشأ بند داخلي لا فاتورة مفاجئة.","Payment provider degraded":"تراجع خدمة مزوّد الدفع","First failed authorisation, Nadi Group":"أول تفويض فاشل · مجموعة نادي","Threshold crossed, incident opened automatically":"تجاوز الحد · فُتحت حادثة تلقائياً","Provider confirmed degraded service":"أكّد المزوّد تراجع الخدمة","Three affected tenants notified":"أُبلغ ثلاثة مستأجرين متأثرين","Authorisations recovering":"التفويضات تتحسّن","All queued payments submitted, none charged twice":"أُرسلت كل الدفعات المُدرَجة ولم يُخصم من أحد مرتين","START AN IMPERSONATION SESSION · TIER 4":"ابدأ جلسة انتحال هوية · الدرجة الرابعة","Access Nadi Group as an administrator":"الوصول إلى مجموعة نادي كمسؤول","You will see their real member data, including names, phone numbers, payment records and health notes. Nadi Group is notified immediately and this session appears in an audit log they can read.":"سترى بيانات أعضائهم الحقيقية، بما فيها الأسماء وأرقام الهواتف وسجلات الدفع والملاحظات الصحية. تُبلَّغ مجموعة نادي فوراً وتظهر هذه الجلسة في سجل تدقيق يستطيعون قراءته.","WHY · REQUIRED, AND THEY WILL READ IT":"السبب · مطلوب وسيقرأونه","Support ticket #4182 — Rania reports the Khalda class roster showing the wrong coach":"تذكرة دعم #4182 — رانيا تبلّغ أن قائمة حصص خلدا تُظهر مدرباً خطأ","FOR HOW LONG":"لكم من الوقت","ACCESS LEVEL":"مستوى الوصول","Read only":"قراءة فقط","Can act":"إمكانية التعديل","Read-only is the default and covers most support work. “Can act” requires a second Veyro approver and is limited to 30 minutes regardless of what is selected above.":"القراءة فقط هي الافتراضي وتكفي لمعظم أعمال الدعم. أما «إمكانية التعديل» فتحتاج موافقاً ثانياً من Veyro وتقتصر على ٣٠ دقيقة أياً كان المحدد أعلاه.","Start read-only session":"ابدأ جلسة قراءة فقط","Nutrition photo logging":"تسجيل الوجبات بالصور","All tenants":"جميع المستأجرين","New booking engine":"محرّك الحجز الجديد","API access":"واجهة البرمجة","Enterprise only":"المؤسسات فقط","Arabic Coach app":"تطبيق المدرب بالعربية","Nadi Group only":"مجموعة نادي فقط","Anything touching money or access needs a second approver before it changes. Every change is logged with who and why.":"أي شيء يمسّ المال أو الدخول يحتاج موافقاً ثانياً قبل تغييره. وكل تغيير يُسجّل بمن ولماذا.","All regions":"جميع المناطق","Web application":"تطبيق الويب","JoFotara submission queue":"قائمة إرسال جوفوترة","Access hardware sync":"مزامنة أجهزة الدخول","WhatsApp delivery":"تسليم رسائل واتساب","Search index":"فهرس البحث","The JoFotara queue holds three invoices that were rejected for a missing buyer tax number. They resubmit once the field is corrected — not a system fault.":"قائمة جوفوترة تحتفظ بثلاث فواتير رُفضت لنقص الرقم الضريبي للمشتري. وتُرسل من جديد عند تصحيح الحقل — لا خلل في النظام.","August · 1 failure":"آب · حالة فشل واحدة","Paid 1 Aug":"دُفعت ١ آب","FAILED · retry 2 of 3":"فاشلة · المحاولة ٢ من ٣","BEFORE YOU SUSPEND STUDIO NINE":"قبل إيقاف ستوديو ناين","Suspending stops check-in for 214 members and locks their staff out of the app. Their card expired — a message usually fixes it faster than a suspension.":"الإيقاف يمنع دخول ٢١٤ عضواً ويحجب موظفيهم عن التطبيق. بطاقتهم منتهية — ورسالة تحل الأمر عادة أسرع من الإيقاف.","Suspend · needs approval":"أوقف · يتطلب موافقة","Internal. Staff sign-in only.":"داخلي. دخول الموظفين فقط.","Continue with Veyro SSO":"تابع بحساب Veyro الموحّد","There is no password option. Two-factor is required and cannot be turned off — this console can reach customer data.":"لا يوجد خيار كلمة سر. التحقق الثنائي مطلوب ولا يمكن تعطيله — فهذه اللوحة تصل إلى بيانات العملاء.","Ticket #4182":"تذكرة #4182","Nadi Group · Rania Haddad · 2 hours ago":"مجموعة نادي · رانيا حداد · قبل ساعتين","Reported from Admin → Scheduling → 19:00 Thursday":"مُبلّغ عنها من الإدارة ← الجدولة ← الخميس ١٩:٠٠","WHAT WE CAN SEE WITHOUT OPENING THEIR DATA":"ما نراه دون فتح بياناتهم","Version 4.18.2 · current\nNo errors logged on that screen\nClass assignment changed twice yesterday\nNo open incidents":"الإصدار 4.18.2 · الحالي\nلا أخطاء مسجّلة على تلك الشاشة\nتغيّر إسناد الحصة مرتين أمس\nلا حوادث مفتوحة","The change history suggests a stale assignment rather than a bug. Try that before opening their records — impersonation is the last resort, not the first.":"سجل التغييرات يشير إلى إسناد قديم لا إلى خلل. جرّب ذلك قبل فتح سجلاتهم — انتحال الهوية آخر الحلول لا أولها.","Hasn't trained in 19 days. Last session he squatted 82.5kg for 5 — don't open there.":"لم يتدرب منذ ١٩ يوماً. في آخر حصة رفع ٨٢٫٥ كغ خمس مرات — لا تبدأ من هناك.","See his profile first":"اعرض ملفه أولاً","LATER TODAY":"لاحقاً اليوم","upper body · on track":"الجسم العلوي · على المسار","asked about her plan":"سألت عن خطتها","Spin · 18 booked":"سبينينغ · ١٨ محجوزة","covering for Omar":"بدلاً من عمر","Generated in 4 seconds · not assigned yet":"أُنشئت في ٤ ثوان · لم تُسند بعد","VEYRO DREW THIS FROM HIS RECORD":"استخرج Veyro هذا من سجله","Based on his last weigh-in 6 days ago and his logged training.":"بناءً على آخر وزن قبل ٦ أيام وتدريبه المسجّل.","Day 1":"اليوم ١","BREAKFAST · 07:30":"الفطور · ٠٧:٣٠","Oats, banana, whey, almond butter":"شوفان وموز وواي بروتين وزبدة لوز","Chicken mansaf-style with rice and yoghurt":"دجاج على طريقة المنسف مع أرز ولبن","Lactose-free yoghurt substituted automatically":"استُبدل اللبن بخالٍ من اللاكتوز تلقائياً","POST-TRAINING · 18:15":"بعد التدريب · ١٨:١٥","DINNER · 20:30":"العشاء · ٢٠:٣٠","Beef kofta, salad, flatbread":"كفتة لحم وسلطة وخبز","Week 8 of 12 · 4 credits left":"الأسبوع ٨ من ١٢ · ٤ حصص متبقية","Was coming 3× a week. No message, no cancellation — he just stopped. Session today at 09:45.":"كان يأتي ٣ مرات أسبوعياً. لا رسالة ولا إلغاء — توقّف فقط. حصته اليوم ٠٩:٤٥.","CURRENT PROGRAMME":"البرنامج الحالي","Lower-body strength · 12 weeks":"قوة الجسم السفلي · ١٢ أسبوعاً","LAST SESSION · 31 JULY":"آخر حصة · ٣١ تموز","Squat 82.5 × 5 · RDL 100 × 8 · leg press 180 × 10":"سكوات ٨٢٫٥ × ٥ · رفعة رومانية ١٠٠ × ٨ · دفع أرجل ١٨٠ × ١٠","Limitations":"القيود الصحية","Left knee — previous meniscus surgery, 2019. No deep loaded flexion. Recorded at intake.":"الركبة اليسرى — جراحة غضروف سابقة ٢٠١٩. لا ثني عميق محمّل. مسجّل عند الالتحاق.","Start today's session":"ابدأ حصة اليوم","His nutrition plan":"خطته الغذائية","Lower body · week 8 of 12":"الجسم السفلي · الأسبوع ٨ من ١٢","Left knee, meniscus repair 2019. No deep loaded flexion.":"الركبة اليسرى · إصلاح غضروف ٢٠١٩. لا ثني عميق محمّل.","Box squat 4 × 6 · from 60kg\nRomanian deadlift 3 × 8\nLeg press 3 × 10\nWalking lunge 3 × 12\nCalf raise 4 × 15":"سكوات على صندوق ٤ × ٦ · من ٦٠ كغ\nرفعة رومانية ٣ × ٨\nدفع الأرجل ٣ × ١٠\nخطوات أمامية ٣ × ١٢\nرفع السمانة ٤ × ١٥","Box squat 55.0 × 6, 6, 5\nRomanian deadlift 90.0 × 8, 8\nLeg press 160 × 10, 10":"سكوات على صندوق ٥٥٫٠ × ٦ · ٦ · ٥\nرفعة رومانية ٩٠٫٠ × ٨ · ٨\nدفع الأرجل ١٦٠ × ١٠ · ١٠","Knee felt tight on set 2. Dropped to 55 rather than pushing.":"الركبة كانت مشدودة في المجموعة الثانية. أنزلته إلى ٥٥ بدل الدفع.","Credit 7 of 10 used · 3 remaining\nAhmad sees the session in his app\nYour verification queue drops to 21":"استُخدمت الحصة ٧ من ١٠ · ٣ متبقية\nيرى أحمد الحصة في تطبيقه\nقائمة التوثيق لديك تنزل إلى ٢١","STARTED FROM A TEMPLATE, ADJUSTED FOR HIM":"بدأت من قالب وعُدّلت له","Deep squats replaced with box squats — his intake records a 2019 meniscus repair with no deep loaded flexion.":"استُبدل السكوات العميق بسكوات على صندوق — سجل التحاقه يذكر إصلاح غضروف ٢٠١٩ دون ثني عميق محمّل.","Wk 1–4":"أسبوع ١–٤","Progression: +2.5kg on the main lift each week if all sets complete. Applied to weeks 5–12 automatically.":"التدرّج: +٢٫٥ كغ على الرفعة الأساسية كل أسبوع إن أُكملت المجموعات. يُطبَّق على الأسابيع ٥–١٢ تلقائياً.","Quads · barbell, box":"الأمامية · بار وصندوق","Quads · barbell":"الأمامية · بار","Quads · machine":"الأمامية · جهاز","Quads · dumbbell":"الأمامية · دمبل","Hamstrings · barbell":"الخلفية · بار","Hamstrings · machine":"الخلفية · جهاز","Box squat is flagged as the substitute for a recorded knee limitation. Adding a deep-flexion movement will warn, not block.":"السكوات على صندوق مُعلَّم كبديل لقيد ركبة مسجّل. وإضافة حركة ثني عميق ستنبّه لا تمنع.","Monday, Wednesday, Friday":"الإثنين والأربعاء والجمعة","Since March 2024":"منذ آذار ٢٠٢٤","Box squat 55.0 × 6 · best\nRomanian deadlift 100 × 8\nLeg press 180 × 10":"سكوات على صندوق ٥٥٫٠ × ٦ · الأفضل\nرفعة رومانية ١٠٠ × ٨\nدفع الأرجل ١٨٠ × ١٠","Intake · Rana Sabbagh":"الالتحاق · رنا صباغ","Lose weight · 3 days a week · prefers classes":"خسارة وزن · ٣ أيام أسبوعياً · تفضّل الحصص","ANYTHING TO WORK AROUND":"أي قيود نراعيها","Injuries, conditions, medication…":"إصابات · حالات · أدوية…","Whatever you record here flags in the programme builder when it conflicts. It warns, it doesn't block — you decide.":"ما تسجّله هنا يُنبّه في منشئ البرامج عند التعارض. ينبّه ولا يمنع — والقرار لك.","Anything clinical needs someone qualified for that in your market. Veyro does not decide what counts as clinical.":"أي شيء طبي يحتاج مختصاً مؤهلاً في سوقك. وVeyro لا يحدد ما يُعدّ طبياً.","Save and build her programme":"احفظ وابنِ برنامجها","Day 1 of 7 · 2,150 kcal":"اليوم ١ من ٧ · ٢١٥٠ سعرة","LUNCH":"الغداء","Chicken with rice":"دجاج مع أرز","AFTER TRAINING":"بعد التدريب","DINNER":"العشاء","Beef kofta, salad":"كفتة لحم وسلطة","Copy this day across the week, or leave the other six as generated.":"انسخ هذا اليوم على الأسبوع، أو اترك الستة الأخرى كما أُنشئت.","Send the changes to Ahmad":"أرسل التغييرات لأحمد","Check-in received Monday":"وصل التقييم الإثنين","down 0.6":"أقل بـ٠٫٦","STUCK TO IT":"الالتزام","days on plan":"أيام على الخطة","WHAT HE SAID":"ما قاله","WHAT HE ACTUALLY LOGGED":"ما سجّله فعلاً","Protein averaged 148g against a 165g target\nTwo shawarma plates on Friday and Saturday\nWeekday meals matched the plan":"متوسط البروتين ١٤٨ غ مقابل هدف ١٦٥ غ\nطبقا شاورما الجمعة والسبت\nوجبات أيام الأسبوع مطابقة للخطة","Adjust his targets":"عدّل أهدافه","Message him":"راسله","Sorry I missed last week, work has been heavy":"آسف على تفويت الأسبوع الماضي، العمل كان مزدحماً","No problem at all. Shall we keep Wednesday 09:45 going forward?":"لا مشكلة إطلاقاً. نثبّت الأربعاء ٠٩:٤٥ من الآن؟","Yes that works":"نعم يناسبني","Is the knee thing still a worry?":"هل ما زالت الركبة مصدر قلق؟","Members can't see their remaining credits until you confirm these happened. Nothing is billed either.":"لا يرى الأعضاء حصصهم المتبقية حتى توثّق حدوثها. ولا يُحتسب شيء أيضاً.","Coach · Khalda":"مدرب · خلدا","Mon–Fri 08:00–18:00\nSaturday 09:00–13:00\nSunday closed":"الإثنين–الجمعة ٠٨:٠٠–١٨:٠٠\nالسبت ٠٩:٠٠–١٣:٠٠\nالأحد مغلق","NASM CPT · expires March 2027\nFirst aid · expires November 2025":"NASM CPT · تنتهي آذار ٢٠٢٧\nالإسعافات الأولية · تنتهي تشرين الثاني ٢٠٢٥","Arabic · your clients see Arabic by default":"العربية · يرى عملاؤك العربية افتراضياً","On a shared gym iPad, face unlock is off and you are signed out after fifteen minutes — client health details are on this device.":"على جهاز مشترك في النادي، فتح الوجه معطّل ويتم إخراجك بعد خمسة عشر دقيقة — فبيانات العملاء الصحية على هذا الجهاز.","Instead of chicken and rice":"بدلاً من الدجاج والأرز","Same calories and protein, no fish, lactose-free.":"نفس السعرات والبروتين · بلا سمك · خالٍ من اللاكتوز.","Beef shawarma plate":"طبق شاورما لحم","Grilled chicken shish tawook":"شيش طاووق مشوي","Lentil soup and two flatbreads":"شوربة عدس ورغيفان","Classes":"الحصص","Khalda · this week":"خلدا · هذا الأسبوع","Thursday 19:00 · with Dana":"الخميس ١٩:٠٠ · مع دانا","Full · 3 on the waitlist":"ممتلئة · ٣ في قائمة الانتظار","Join the waitlist":"انضم لقائمة الانتظار","Thursday 07:00 · with Yousef":"الخميس ٠٧:٠٠ · مع يوسف","Friday 18:00 · with Dana":"الجمعة ١٨:٠٠ · مع دانا","Auto-booking from the waitlist is opt-in. Being charged for a class you did not know you got is a support ticket every time.":"الحجز التلقائي من قائمة الانتظار اختياري. فأن تُحاسب على حصة لم تعلم أنك حصلت عليها يفتح تذكرة دعم كل مرة.","Welcome to Khalda,\nAhmad":"أهلاً بك في خلدا،\nأحمد","Three quick things and we'll get out of your way.":"ثلاثة أمور سريعة ثم نتركك.","WHAT ARE YOU AFTER":"ما تسعى إليه","Lose weight":"خسارة الوزن","Get stronger":"زيادة القوة","Just stay active":"المحافظة على النشاط","We'll text you a code — no password to remember.":"سنرسل لك رمزاً — بلا كلمة سر تحفظها.","PHONE NUMBER":"رقم الهاتف","Use the number your club has on file and we'll find your membership automatically.":"استخدم الرقم المسجّل عند ناديك وسنجد عضويتك تلقائياً.","Lower body":"الجسم السفلي","With Yousef · 09:45 · about 45 minutes":"مع يوسف · ٠٩:٤٥ · نحو ٤٥ دقيقة","Done · 6":"تم · ٦","Couldn't finish? Tap the weight to change it.":"لم تُكمل؟ اضغط الوزن لتغييره.","Saves offline · no coach needed":"يُحفظ دون اتصال · بلا حاجة لمدرب","Done.\n41 minutes.":"انتهيت.\n٤١ دقيقة.","Five exercises, 18 sets. Your box squat is up 5kg since week 5.":"خمسة تمارين و١٨ مجموعة. سكوات الصندوق لديك أعلى بـ٥ كغ منذ الأسبوع ٥.","PERSONAL BEST":"أفضل رقم شخصي","Box squat · 55kg × 6":"سكوات على صندوق · ٥٥ كغ × ٦","Previous best 50kg × 6, three weeks ago.":"الأفضل سابقاً ٥٠ كغ × ٦ قبل ثلاثة أسابيع.","Next session Friday at 09:45 with Yousef.":"الحصة القادمة الجمعة ٠٩:٤٥ مع يوسف.","Back to today":"رجوع إلى اليوم","Upper body":"الجسم العلوي","Last Friday":"الجمعة الماضية","Last Wednesday":"الأربعاء الماضي","Today's food":"طعام اليوم","Search":"بحث","My grocery list →":"قائمة الشراء ←","Lunch · 680 kcal":"الغداء · ٦٨٠ سعرة","WHAT'S IN IT":"مكوّناتها","Yoghurt swapped for lactose-free automatically — Yousef knows about that.":"استُبدل اللبن بخالٍ من اللاكتوز تلقائياً — ويوسف يعلم بذلك.","Show me something else":"اعرض لي شيئاً آخر","Shawarma plate":"طبق شاورما","Beef · 665 kcal":"لحم · ٦٦٥ سعرة","Mansaf":"منسف","Chicken · 720 kcal":"دجاج · ٧٢٠ سعرة","Labneh and bread":"لبنة وخبز","Falafel wrap":"لفة فلافل","Favourite":"المفضلة","Portions are in plates and pieces, not grams. Nobody weighs a shawarma.":"المقادير بالأطباق والقطع لا بالغرامات. لا أحد يزن الشاورما.","Al Rabie orange juice 250ml":"عصير برتقال الربيع ٢٥٠ مل","If we don't recognise something, you can add it by hand and the barcode gets attached for next time.":"إن لم نتعرّف على شيء يمكنك إضافته يدوياً ويُربط الباركود للمرة القادمة.","OUR GUESS — CHECK IT'S RIGHT":"تقديرنا — تحقق من صحته","Grilled chicken, rice, salad. Roughly 640 kcal.":"دجاج مشوي وأرز وسلطة. نحو ٦٤٠ سعرة.","A guess from the photo, not a measurement. Adjust it if it looks wrong — Yousef sees what you log, not what we guessed.":"تقدير من الصورة لا قياس. عدّله إن بدا خطأ — يوسف يرى ما تسجّله لا ما قدّرناه.","This week · 8 things":"هذا الأسبوع · ٨ أصناف","Chicken breast":"صدور دجاج","Beef mince":"لحم مفروم","Rice":"أرز","Lactose-free yoghurt":"لبن خالٍ من اللاكتوز","Oats":"شوفان","Bananas":"موز","Dates":"تمر","Flatbread":"خبز","Built from this week's meals. Anything you have already eaten drops off the list.":"مبنية على وجبات هذا الأسبوع. وما أكلته يسقط من القائمة.","Down 0.6 kg from last week":"أقل بـ٠٫٦ كغ من الأسبوع الماضي","Spin with Dana":"سبينينغ مع دانا","Thursday 19:00":"الخميس ١٩:٠٠","Studio 2, Khalda\nBike 7 held for you\n45 minutes":"الاستوديو ٢ · خلدا\nالدراجة ٧ محفوظة لك\n٤٥ دقيقة","Bring water and a towel. Arrive five minutes early — bikes are released at 19:00.":"خذ ماء ومنشفة. واحضر قبل خمس دقائق — تُحرَّر الدراجات ١٩:٠٠.","Free to cancel until 17:00 Thursday. After that it counts as attended.":"الإلغاء مجاني حتى ١٧:٠٠ الخميس. وبعدها تُحسب حضوراً.","Thursday 19:00 · Dana · Studio 2":"الخميس ١٩:٠٠ · دانا · الاستوديو ٢","Saturday 10:00 · Nour · Studio 1":"السبت ١٠:٠٠ · نور · الاستوديو ١","WAITLIST 2":"قائمة انتظار · ٢","Last Thursday · Studio 2":"الخميس الماضي · الاستوديو ٢","Saturday Yoga":"يوغا السبت","You're second on the list":"أنت الثاني في القائمة","Two people ahead of you. Places usually open up — nine of the last ten waitlists at this class cleared by the morning of.":"شخصان أمامك. والأماكن تُفتح عادة — تسع من آخر عشر قوائم انتظار لهذه الحصة انتهت صباح يومها.","We'll book you automatically and let you know. You can turn that off if you'd rather decide yourself.":"سنحجز لك تلقائياً ونخبرك. ويمكنك تعطيل ذلك إن فضّلت أن تقرر بنفسك.","Book me automatically · on":"احجز لي تلقائياً · مفعّل","Cancel Spin?":"إلغاء السبينينغ؟","Thursday 19:00 with Dana":"الخميس ١٩:٠٠ مع دانا","You're inside the free window — cancelling now costs nothing and your bike goes to the next person on the waitlist.":"أنت داخل مدة الإلغاء المجاني — لا يكلّفك شيئاً وتذهب دراجتك لمن يليك في قائمة الانتظار.","Booking uses one of your three remaining credits. They run out in November.":"الحجز يستخدم حصة من ثلاث متبقية. وتنتهي في تشرين الثاني.","Down 4.1 kg since March. Steady rather than sharp, which is what Yousef was aiming for.":"أقل بـ٤٫١ كغ منذ آذار. تدريجي لا حاد، وهو ما كان يوسف يستهدفه.","Box squat 55.0 kg × 6\nRomanian deadlift 100 kg × 8\nLeg press 180 kg × 10":"سكوات على صندوق ٥٥٫٠ كغ × ٦\nرفعة رومانية ١٠٠ كغ × ٨\nدفع الأرجل ١٨٠ كغ × ١٠","Private to you. Share with Yousef whenever you like — you can stop sharing at any point.":"خاصة بك. شاركها مع يوسف وقتما شئت — ويمكنك التوقف في أي لحظة.","Your membership":"عضويتك","All opening hours at Khalda\nAll group classes\nGuest pass once a month":"جميع ساعات العمل في خلدا\nكل الحصص الجماعية\nتصريح زائر شهرياً","Started 4 March 2024\n12-month term, ends March 2026\nFrozen 1 month of 3 this year":"بدأت ٤ آذار ٢٠٢٤\nمدة ١٢ شهراً تنتهي آذار ٢٠٢٦\nجُمّدت شهراً من ثلاثة هذا العام","If you cancel before March there's a two-month fee. Freezing is free and pauses everything.":"إن ألغيت قبل آذار فهناك رسم شهرين. والتجميد مجاني ويوقف كل شيء.","Cancel is present, plainly worded, and last. Hiding it behind a phone call is the pattern members hate most and regulators increasingly forbid.":"الإلغاء موجود وبصيغة واضحة وفي الآخر. وإخفاؤه خلف مكالمة هاتفية أكثر ما يكرهه الأعضاء وما تمنعه الجهات التنظيمية تدريجياً.","Club · JOD 55.00 a month":"كلب · JOD 55.00 شهرياً","While frozen you won't be charged and won't be able to train. Your price stays the same when you come back.":"أثناء التجميد لا تُحاسب ولا تستطيع التدريب. وسعرك يبقى كما هو عند عودتك.","You've used 1 of 3 freeze months this year.":"استخدمت شهراً من ثلاثة للتجميد هذا العام.","Frozen 1 September to 30 September. Billing restarts 1 October.":"مجمّدة من ١ أيلول إلى ٣٠ أيلول. وتعود الفواتير ١ تشرين الأول.","Your club approves freezes, so this is a request rather than an instant change.":"ناديك هو من يوافق على التجميد، فهذا طلب لا تغيير فوري.","Your August membership. Your card ending 4417 expired, so pick another way.":"عضوية آب. بطاقتك المنتهية بـ4417 انتهت صلاحيتها، فاختر طريقة أخرى.","From your bank app · instant":"من تطبيق مصرفك · فوري","A different card":"بطاقة أخرى","Saved for next month if you want":"تُحفَظ للشهر القادم إن أردت","Pay at the desk":"ادفع في الاستقبال","Cash or card, next time you're in":"نقداً أو بالبطاقة في زيارتك القادمة","Pay with CliQ":"ادفع بكليك","You can keep training either way — nothing is blocked. Your receipt arrives on WhatsApp.":"يمكنك التدريب في الحالتين — لا شيء محجوب. ويصلك الإيصال على واتساب.","Expired July 2026":"انتهت تموز ٢٠٢٦","Add a second way to pay and we'll use it if the first one fails — most missed payments are just an expired card.":"أضف طريقة دفع ثانية ونستخدمها إن فشلت الأولى — فأكثر الدفعات المتعثرة سببها بطاقة منتهية.","Wallet":"المحفظة","Hold this at the turnstile":"ضعه أمام البوابة","This works without a signal. If the turnstile won't read it, the front desk can let you in.":"يعمل دون تغطية. وإن لم تقرأه البوابة يستطيع الاستقبال إدخالك.","How is the knee feeling after Wednesday?":"كيف الركبة بعد الأربعاء؟","Better actually. The box squats helped":"أفضل فعلاً. سكوات الصندوق ساعد","Good. Keep it at 55 this week and we will see":"جيد. ثبّت على ٥٥ هذا الأسبوع ونرى","Message Yousef":"راسل يوسف","August payment did not go through":"لم تُنفَّذ دفعة آب","About your knee":"بخصوص ركبتك","Spin confirmed":"تأكيد السبينينغ","Thursday 19:00, bike 7":"الخميس ١٩:٠٠ · الدراجة ٧","You hit a new best":"حققت رقماً جديداً","Box squat 55 kg × 6":"سكوات على صندوق ٥٥ كغ × ٦","Member since March 2024":"عضو منذ آذار ٢٠٢٤","Lose weight · train 4 days a week":"خسارة الوزن · التدريب ٤ أيام أسبوعياً","No fish\nLactose sensitive":"بلا سمك\nحساسية اللاكتوز","Privacy and what you share":"الخصوصية وما تشاركه","On":"مفعّل","Last changed 11 months ago":"آخر تغيير قبل ١١ شهراً","iPhone · Amman · now\niPad · Amman · 3 weeks ago":"آيفون · عمّان · الآن\nآيباد · عمّان · قبل ٣ أسابيع","Offers and news":"العروض والأخبار","You turned this off in July":"أوقفتها في تموز","He uses it to adjust your plan":"يستخدمه لتعديل خطتك","Nothing shared yet":"لم تُشارك شيئاً بعد","Health details":"التفاصيل الصحية","Only your coach and the club":"مدربك والنادي فقط","You can ask for a copy of everything we hold about you, or ask us to delete your account.":"يمكنك طلب نسخة من كل ما نحفظه عنك، أو طلب حذف حسابك.","Your workout and your plan are on your phone already. Anything you log will send itself when you're back in range.":"تدريبك وخطتك على هاتفك أصلاً. وما تسجّله يُرسل نفسه عند عودة التغطية.","Start the session":"ابدأ الحصة","Booking a class\nPaying anything\nMessaging Yousef":"حجز حصة\nدفع أي مبلغ\nمراسلة يوسف","Your entry pass still works — it does not need a signal.":"تصريح دخولك يعمل — لا يحتاج تغطية."};

  function T(s) {
    if (LANG !== 'ar' || typeof s !== 'string' || !s) return s;
    if (AR[s]) return AR[s];
    // sentence with a trailing/leading space or punctuation variance
    var k = s.trim();
    if (AR[k]) return AR[k];
    return s;
  }
  function Tkids(k) {
    if (LANG !== 'ar') return k;
    if (typeof k === 'string') return T(k);
    return k;
  }


  // A string with digits and no Arabic is a measurement, count, date or amount: it must
  // render LTR whatever the surrounding paragraph direction is.
  var AR_RE = /[\u0600-\u06FF\u0750-\u077F]/;
  function numeric(k) { return typeof k === 'string' && /[0-9]/.test(k) && !AR_RE.test(k); }
  function bidiKids(k) {
    if (!numeric(k)) return k;
    return h('span', { dir: 'ltr', style: { unicodeBidi: 'isolate' } }, k);
  }
  function D(s, k) { return h('div', { style: s }, bidiKids(Tkids(k))); }
  function Btn(on, s, txt) { return h('div', { onClick: on, style: Object.assign({ cursor: 'pointer', userSelect: 'none' }, s) }, bidiKids(Tkids(txt))); }
  function prim(txt, on, big) {
    return Btn(on, { minHeight: DARK || big ? 44 : undefined, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', font: '500 ' + (big ? 14 : 12) + 'px/1 ' + sans, background: DARK ? C.dAcc : C.ink, color: DARK ? '#12233d' : C.surf, padding: big ? '15px 17px' : '11px 14px', borderRadius: 6, display: 'inline-block' }, txt);
  }
  function sec(txt, on, big) {
    return Btn(on, { minHeight: DARK || big ? 44 : undefined, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', font: '500 ' + (big ? 14 : 12) + 'px/1 ' + sans, border: '1px solid ' + (DARK ? 'rgba(255,255,255,.24)' : 'rgba(23,23,26,.28)'), color: DARK ? C.dT1 : C.t1, padding: big ? '14px 16px' : '10px 13px', borderRadius: 6, display: 'inline-block' }, txt);
  }
  function ghost(txt, on) { return Btn(on, { font: '400 11.5px/1 ' + sans, color: DARK ? C.dT2 : C.t2, padding: '11px 6px' }, txt); }
  function eyebrow(txt, col) { return D({ font: '500 9.5px/1.4 ' + mono, color: col || C.t2, letterSpacing: '.07em' }, txt); }
  function badge(txt, col) { return D({ font: '500 9.5px/1.4 ' + mono, color: col, border: '1px solid ' + col, padding: '2px 6px', borderRadius: 3, display: 'inline-block' }, txt); }
  function page(kids, pad) { return D({ padding: pad || '20px 22px 28px', display: 'flex', flexDirection: 'column', gap: 16, background: C.canvas, minHeight: '100%' }, kids); }
  function card(kids, extra) { return D(Object.assign({ border: '1px solid ' + C.line, borderRadius: 4, background: C.surf, overflow: 'hidden' }, extra || {}), kids); }
  function h1(txt, sub) {
    return D({}, [
      D({ font: '500 24px/1.18 ' + sans, letterSpacing: '-.018em' }, txt),
      sub ? D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 5 }, sub) : null
    ]);
  }
  function metrics(items) {
    return D({ display: 'grid', gridTemplateColumns: 'repeat(' + items.length + ',minmax(0,1fr))', gap: 1, background: 'rgba(23,23,26,.12)', border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden' },
      items.map(function (m, i) {
        return D({ background: C.surf, padding: '13px 15px', key: i }, [
          eyebrow(m[0]),
          D({ font: '500 21px/1.15 ' + mono, marginTop: 7, color: m[3] || C.t1 }, m[1]),
          D({ font: '400 11px/1.4 ' + sans, color: C.t2, marginTop: 5 }, m[2])
        ]);
      }).map(function (n, i) { return h('div', { key: i, style: { background: C.surf, padding: '13px 15px' } }, n.props.children); })
    );
  }
  function attn(o) {
    return D({ display: 'flex', borderTop: o.first ? 'none' : '1px solid ' + C.hair, background: o.dim ? C.sunk : C.surf }, [
      D({ width: 3, background: o.sev, flexShrink: 0 }),
      D({ flex: 1, padding: o.dim ? '11px 15px' : '13px 15px', minWidth: 0 }, o.dim
        ? D({ display: 'flex', gap: 11, alignItems: 'center', flexWrap: 'wrap' }, [
            badge(o.tag, o.sev),
            D({ font: '450 13px/1.4 ' + sans, flex: 1, minWidth: 200 }, o.title),
            o.owner ? D({ font: '400 10.5px/1.4 ' + mono, color: C.t4 }, o.owner) : null,
            o.action ? sec(o.action, o.on) : null
          ])
        : [
            D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [
              badge(o.tag, o.sev),
              D({ font: '400 10.5px/1.4 ' + mono, color: C.t2 }, o.when),
              D({ flex: 1 }),
              o.money ? D({ font: '500 15px/1.2 ' + mono, color: o.sev === C.err ? C.err : C.t1 }, o.money) : null,
              o.moneyNote ? D({ font: '400 9.5px/1.4 ' + mono, color: C.t2 }, o.moneyNote) : null
            ]),
            D({ font: '500 15.5px/1.35 ' + sans, marginTop: 7 }, o.title),
            D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 4, maxWidth: '88ch' }, o.body),
            D({ display: 'flex', gap: 8, marginTop: 11, flexWrap: 'wrap', alignItems: 'center' },
              [o.primary ? prim(o.primary, o.on) : null, o.secondary ? sec(o.secondary, o.on2) : null, o.snooze ? ghost('Snooze', o.onSnooze) : null])
          ])
    ]);
  }

  // ---------- DESKTOP ----------
  var S = {};

  S['ADM-CC-01'] = function (v) {
    var done = v.resolvedIds.indexOf('pay') >= 0;
    var scope = v.loc === 'All locations' ? 'all locations' : v.loc;
    var head = done ? 'Two things need you this morning' : 'Three things need you this morning';
    return page([
      D({ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 280 }, h1(head, 'Wednesday 19 August · ' + scope + ' · data through 08:38')),
        D({ display: 'flex', gap: 7 }, [sec('Today'), ghost('7 days'), ghost('Month')])
      ]),
      metrics([
        ['COLLECTED · MONTH TO DATE', 'JOD 41,280', '↓ 7.8% vs July · pace to 63.1k'],
        ['ACTIVE MEMBERS', '4,812', '+38 this month'],
        ['VISITS TODAY', '218', 'usual for a Wednesday'],
        ['LEAD CONVERSION · 30D', '31%', 'target 30% · 36 open']
      ]),
      D({}, [
        D({ display: 'flex', gap: 10, alignItems: 'baseline', marginBottom: 9, flexWrap: 'wrap' }, [
          D({ font: '500 14.5px/1.3 ' + sans }, 'Needs you now'),
          D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, (done ? '8 open · 1 critical' : '9 open · 2 critical')),
          D({ flex: 1 }),
          Btn(function () { v.openScreen('ADM-CC-07'); }, { font: '400 11px/1.4 ' + sans, color: C.ink }, 'Show resolved today')
        ]),
        card(D({}, [
          done ? null : attn({
            first: true, sev: C.err, tag: 'MONEY', when: '2h ago · Khalda, Abdoun',
            money: 'JOD 312.00', moneyNote: 'at risk', title: '6 payments failed overnight',
            body: 'Four expired cards, two insufficient funds. Veyro retried each twice and drafted a message for every member. No access is blocked — all six can train today.',
            primary: 'Send 6 payment links', on: function () { v.act('resolve', 'pay'); },
            secondary: 'Review each', on2: function () { v.openScreen('ADM-PAY-05'); },
            snooze: true, onSnooze: function () { v.act('flash', 'Snoozed until tomorrow 08:00'); }
          }),
          attn({
            first: done, sev: C.err, tag: 'COMPLIANCE', when: 'since 09:14 yesterday · Sweifieh',
            title: 'JoFotara rejected 3 invoices',
            body: 'All three are missing a buyer tax number. The sales are recorded and the money is collected — only the e-invoice submission failed. Correct the field and they resubmit automatically.',
            primary: 'Fix the 3 invoices', on: function () { v.openScreen('ADM-PAY-03'); },
            secondary: 'What is JoFotara?', on2: function () { v.openScreen('ADM-SET-03'); }
          }),
          attn({
            sev: C.warn, tag: 'RETENTION', when: 'this week · ' + scope, money: 'JOD 4,760.00', moneyNote: 'renewal value',
            title: '14 memberships expire within 7 days',
            body: 'Nine have trained in the last fortnight and historically renew without prompting. Five have not visited in over 20 days — those are the ones worth a call.',
            primary: 'Send offer to the 9', on: function () { v.act('flash', 'Offer sent to 9 members'); },
            secondary: 'Call list for the 5', on2: function () { v.openScreen('ADM-MEM-05'); }
          }),
          attn({ dim: true, sev: C.info, tag: 'STAFFING', title: 'Spin 19:00 Thursday has no coach — 18 members booked', owner: 'Rania', action: 'Open the class', on: function () { v.openScreen('ADM-SCH-02'); } }),
          attn({ dim: true, sev: C.info, tag: 'LEADS', title: '7 leads have gone 48 hours without contact', owner: 'Sales team', action: 'Assign now', on: function () { v.openScreen('ADM-CRM-01'); } }),
          D({ padding: '9px 15px', borderTop: '1px solid ' + C.hair }, Btn(function () { v.openScreen('ADM-CC-06'); }, { font: '400 11.5px/1.4 ' + sans, color: C.ink }, 'Open any item for its full evidence and history →'))
        ]))
      ]),
      D({ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }, [
        D({ flex: '1 1 460px', minWidth: 400, border: '1px solid ' + C.ai, borderRadius: 4, background: C.surf, overflow: 'hidden' }, [
          D({ padding: '9px 14px', background: C.aiWash, display: 'flex', gap: 8, alignItems: 'center' }, [
            D({ font: '400 10.5px/1 ' + mono, color: C.ai }, '✦'),
            D({ font: '500 10px/1.4 ' + mono, color: C.ai, letterSpacing: '.07em' }, 'VEYRO INTERPRETATION · NOT A CONFIRMED FIGURE')
          ]),
          D({ padding: '14px 15px' }, [
            eyebrow('SYSTEM FACT'),
            D({ font: '450 14px/1.55 ' + sans, marginTop: 5 }, 'Collections are JOD 3,490 below the same point in July.'),
            D({ height: 1, background: 'rgba(23,23,26,.1)', margin: '12px 0' }),
            eyebrow("VEYRO'S READING OF WHY", C.ai),
            D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 6 }, '−1,840 PT revenue at Khalda · −1,120 annual renewals · −530 unrecovered failed payments.'),
            D({ display: 'flex', gap: 8, marginTop: 11, flexWrap: 'wrap' }, [
              prim('See the evidence', function () { v.openScreen('ADM-AI-01'); }),
              sec('Open the 31 sessions', function () { v.act('flash', '31 unverified sessions — assigned to Khalda'); })
            ])
          ])
        ]),
        D({ flex: '1 1 300px', minWidth: 280 }, card(D({ padding: '14px 15px' }, [
          D({ font: '500 12.5px/1.3 ' + sans }, 'By location · month to date'),
          D({ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 11 },
            [['Abdoun', '17,940', '+2.1%', C.ok, 100], ['Khalda', '14,110', '−18.4%', C.err, 79], ['Sweifieh', '9,230', '+5.6%', C.ok, 51]].map(function (r, i) {
              return D({ key: i }, [
                D({ display: 'flex', gap: 8, alignItems: 'baseline' }, [
                  D({ font: '450 12px/1.3 ' + sans, flex: 1 }, r[0]),
                  D({ font: '500 12px/1.2 ' + mono }, r[1]),
                  D({ font: '500 10.5px/1.2 ' + mono, color: r[3], width: 46, textAlign: 'end' }, r[2])
                ]),
                D({ height: 3, background: '#ece9e3', marginTop: 5, borderRadius: 2, overflow: 'hidden' }, D({ height: 3, width: r[4] + '%', background: r[3] === C.err ? C.err : C.t2 }))
              ]);
            })),
          D({ font: '400 11.5px/1.55 ' + sans, color: '#3d3b36', marginTop: 10 }, 'Khalda accounts for the entire shortfall.')
        ])))
      ])
    ]);
  };

  S['ADM-CC-06'] = function (v) {
    return page([
      h1('6 payments failed overnight', 'ADM-CC-06 · money · 2 hours old · unassigned'),
      card(D({ padding: '16px 18px' }, [
        eyebrow('WHAT HAPPENED'),
        D({ font: '400 13.5px/1.68 ' + sans, color: '#2c2a26', marginTop: 6, maxWidth: '84ch' }, 'Six scheduled membership charges failed between 06:00 and 06:12. Four cards had expired, two had insufficient funds. Veyro retried each twice on the schedule set in dunning configuration and stopped, as configured, rather than retrying indefinitely.'),
        D({ height: 1, background: 'rgba(23,23,26,.1)', margin: '14px 0' }),
        eyebrow('WHAT IS AFFECTED'),
        D({ font: '400 13.5px/1.68 ' + sans, color: '#2c2a26', marginTop: 6 }, 'JOD 312.00 across 6 members at Khalda and Abdoun. No access is blocked — tenant policy grants 14 days of grace, so all six can train. Nothing was charged twice.'),
        D({ height: 1, background: 'rgba(23,23,26,.1)', margin: '14px 0' }),
        eyebrow('WHAT YOU CAN DO'),
        D({ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }, [
          prim('Open the recovery workspace', function () { v.openScreen('ADM-PAY-05'); }),
          sec('Assign to Nadia', function () { v.act('flash', 'Assigned to Nadia · accounts'); }),
          sec('Snooze 24h', function () { v.act('flash', 'Snoozed until tomorrow 08:00'); })
        ])
      ])),
      card(D({}, [
        D({ padding: '10px 14px', background: C.sunk, borderBottom: '1px solid ' + C.hair }, eyebrow('ACTION HISTORY')),
        D({}, [['06:00', 'Charges attempted · 6 of 218 failed'], ['06:04', 'Retry 1 · all 6 declined'], ['06:12', 'Retry 2 · all 6 declined · dunning stopped'], ['06:13', 'Messages drafted, awaiting approval'], ['08:38', 'Raised to the Command Center']].map(function (r, i) {
          return D({ key: i, display: 'flex', gap: 12, padding: '9px 14px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
            D({ font: '400 10.5px/1.4 ' + mono, color: C.t2, width: 52, flexShrink: 0 }, r[0]),
            D({ font: '400 12px/1.45 ' + sans, flex: 1 }, r[1])
          ]);
        }))
      ]))
    ]);
  };

  S['ADM-CC-07'] = function (v) {
    return page([
      h1('Resolved today', 'ADM-CC-07 · 7 items · read-only'),
      card(D({}, [['Low stock · Khalda', 'Nadia', '08:12', 'Reordered'], ['Document expiry · 3 waivers', 'Layla', '08:31', 'Members messaged'], ['Coach note · Omar', 'Ziad', '09:02', 'Acknowledged'], ['Failed payment · Hala', 'Nadia', '09:14', 'Link sent, paid'], ['Access denial · Tareq', 'Layla', '09:20', 'Day pass sold'], ['Lead uncontacted · 4', 'Sales', '09:44', 'Assigned'], ['Class capacity · Yoga', 'Ziad', '10:02', 'Waitlist opened']].map(function (r, i) {
        return D({ key: i, display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) 110px 68px minmax(0,1fr)', gap: 12, padding: '10px 14px', borderTop: i ? '1px solid ' + C.hair : 'none', alignItems: 'center' }, [
          D({ font: '450 12.5px/1.4 ' + sans }, r[0]),
          D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, r[1]),
          D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, r[2]),
          D({ font: '400 11.5px/1.4 ' + sans, color: C.ok }, r[3])
        ]);
      }))),
      D({ font: '400 12px/1.6 ' + sans, color: C.t2, maxWidth: '80ch' }, 'No un-resolve action exists. A resolution is a record — correcting one means acting again, which appears here as a new row.')
    ]);
  };

  S['ADM-MEM-05'] = function (v) {
    var all = [
      ['Ahmad Nabulsi', 'Club', 'Khalda', 'JOD 55.00', '21 Aug', '19d ago', 'OVERDUE', C.err, 'owes'],
      ['Dana Qasem', 'Club', 'Khalda', 'JOD 45.00', '12 Sep', 'today', 'FAILED', C.err, 'owes'],
      ['Yara Mansour', 'Club+', 'Abdoun', 'JOD 72.00', '—', 'frozen', 'FROZEN', C.info, 'owes'],
      ['Tareq Odeh', 'Flex', 'Khalda', 'JOD 40.00', 'expired', '12d ago', 'EXPIRED', C.err, 'owes'],
      ['Hala Barakat', 'Club', 'Sweifieh', 'JOD 55.00', '3 Sep', '2d ago', 'FAILED', C.err, 'owes'],
      ['Lina Haddad', 'Club+', 'Abdoun', 'JOD 0.00', '24 Aug', 'today', 'EXPIRING 5D', C.warn, 'expiring'],
      ['Omar Zaid', 'Club', 'Khalda', 'JOD 0.00', '23 Aug', '4d ago', 'EXPIRING 4D', C.warn, 'expiring'],
      ['Nour Khoury', 'Flex', 'Sweifieh', 'JOD 0.00', '25 Aug', 'today', 'EXPIRING 6D', C.warn, 'expiring'],
      ['Faris Alami', 'Club', 'Abdoun', 'JOD 45.00', '28 Aug', 'yesterday', 'FAILED', C.err, 'owes'],
      ['Rami Tabbaa', 'Club', 'Khalda', 'JOD 0.00', '14 Sep', '38d ago', 'DORMANT', C.warn, 'dormant']
    ];
    var rows = all.filter(function (r) { return v.filter === 'all' || r[8] === v.filter; })
      .filter(function (r) { return v.loc === 'All locations' || r[2] === v.loc; });
    var canSeeMoney = v.role !== 'Reception';
    var fils = [['Owes money', 'owes'], ['Expiring', 'expiring'], ['Not visited 30d', 'dormant'], ['Everyone', 'all']];
    return page([
      D({ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 250 }, h1('Members', '4,812 active · 312 expired · 68 frozen · ' + v.loc.toLowerCase())),
        prim('Add member', function () { v.openScreen('ADM-MEM-10'); })
      ]),
      card(D({}, [
        D({ padding: '11px 16px', borderBottom: '1px solid ' + C.hair, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }, [
          D({ font: '400 11.5px/1 ' + sans, color: C.t3, border: '1px solid rgba(23,23,26,.16)', background: C.sunk, padding: '8px 11px', borderRadius: 6, minWidth: 200 }, '⌕ Name, phone, email, member ID'),
          D({ width: 1, height: 20, background: 'rgba(23,23,26,.12)' })
        ].concat(fils.map(function (f, i) {
          var on = v.filter === f[1];
          return Btn(function () { v.act('filter', f[1]); }, { key: i, font: (on ? '500' : '400') + ' 11px/1 ' + sans, background: on ? C.t1 : 'transparent', color: on ? C.surf : '#3d3b36', border: on ? '1px solid ' + C.t1 : '1px solid rgba(23,23,26,.2)', padding: '8px 11px', borderRadius: 6 }, f[0]);
        }))),
        v.selected.length ? D({ padding: '9px 16px', background: C.wash, borderBottom: '1px solid ' + C.hair, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
          D({ font: '500 12px/1.3 ' + sans, color: C.ink }, v.selected.length + ' selected'),
          D({ flex: 1 }),
          sec('Send message', function () { v.act('flash', 'Message sent to ' + v.selected.length + ' members'); }),
          canSeeMoney ? sec('Send payment links', function () { v.act('flash', 'Payment links sent to ' + v.selected.length + ' members'); }) : null,
          ghost('Clear', function () { v.act('clearSel'); })
        ]) : null,
        D({ overflowX: 'auto' }, D({ minWidth: 940 }, [
          D({ display: 'grid', gridTemplateColumns: '32px minmax(0,1.3fr) 78px 92px 96px 88px 88px minmax(0,1fr)', gap: 12, padding: '9px 16px', background: C.sunk, borderBottom: '1px solid ' + C.hair, font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' },
            ['', 'MEMBER', 'PLAN', 'CLUB', canSeeMoney ? 'BALANCE' : '', 'RENEWS', 'LAST VISIT', 'STATE'].map(function (x, i) { return D({ key: i }, x); })),
          rows.length ? D({}, rows.map(function (r, i) {
            var on = v.selected.indexOf(r[0]) >= 0;
            return D({ key: i, display: 'grid', gridTemplateColumns: '32px minmax(0,1.3fr) 78px 92px 96px 88px 88px minmax(0,1fr)', gap: 12, padding: '0 16px', height: 34, alignItems: 'center', borderBottom: '1px solid rgba(23,23,26,.06)', background: on ? C.wash : C.surf }, [
              Btn(function () { v.act('select', r[0]); }, { font: '400 11px/1 ' + mono, color: on ? C.ink : C.ctl }, on ? '☑' : '☐'),
              Btn(function () { v.openScreen('ADM-MEM-01'); }, { font: '450 12px/1.3 ' + sans, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, r[0]),
              D({ font: '400 11px/1.3 ' + mono, color: C.t2 }, r[1]),
              D({ font: '400 11px/1.3 ' + mono, color: C.t2 }, r[2]),
              D({ font: '500 11.5px/1.2 ' + mono, color: canSeeMoney ? (r[3] === 'JOD 0.00' ? C.t1 : C.err) : C.t3 }, canSeeMoney ? r[3] : '—'),
              D({ font: '400 11px/1.3 ' + mono, color: C.t2 }, r[4]),
              D({ font: '400 11px/1.3 ' + mono, color: C.t2 }, r[5]),
              D({ font: '500 10px/1.4 ' + mono, color: r[7] }, r[6])
            ]);
          })) : D({ padding: '26px 16px', font: '400 13px/1.6 ' + sans, color: C.t2 }, 'No members match this filter at ' + v.loc + '. Widen the location scope or clear the filter.'),
          D({ padding: '10px 16px', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
            D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, 'Showing ' + rows.length + ' matching · 4,812 total'),
            D({ flex: 1 }),
            canSeeMoney ? sec('Export · needs approval', function () { v.act('flash', 'Export requires a stated reason — tier 4'); }) : null
          ])
        ]))
      ])),
      D({ font: '400 12px/1.6 ' + sans, color: C.t2, maxWidth: '84ch' }, v.role === 'Reception' ? 'You are viewing as Reception: the balance column and Export are absent, not greyed.' : 'Nothing here enumerates 4,812 rows. Filters query server-side and the count states matches against total.')
    ]);
  };

  S['ADM-MEM-01'] = function (v) {
    var tabs = ['Overview', 'Membership', 'Billing', 'Attendance', 'Coaching', 'Documents'];
    var body;
    if (v.tab360 === 'Billing') {
      body = card(D({}, [
        D({ padding: '10px 14px', background: C.sunk, borderBottom: '1px solid ' + C.hair }, eyebrow('INVOICES')),
        D({}, [['INV-20418', '17 Aug', 'JOD 55.00', 'UNPAID', C.err], ['INV-20102', '1 Jul', 'JOD 55.00', 'PAID', C.ok], ['INV-19844', '1 Jun', 'JOD 55.00', 'PAID', C.ok]].map(function (r, i) {
          return Btn(function () { v.openScreen('ADM-PAY-03'); }, { key: i, display: 'grid', gridTemplateColumns: '110px 80px 100px minmax(0,1fr)', gap: 12, padding: '11px 14px', borderTop: i ? '1px solid ' + C.hair : 'none', alignItems: 'center' }, [
            D({ font: '400 11.5px/1.4 ' + mono }, r[0]), D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, r[1]),
            D({ font: '500 12px/1.2 ' + mono }, r[2]), D({ font: '500 10px/1.4 ' + mono, color: r[4] }, r[3])
          ]);
        }))
      ]));
    } else if (v.tab360 === 'Membership') {
      body = card(D({ padding: '15px 17px' }, [
        D({ font: '500 14px/1.35 ' + sans }, 'Club · monthly · JOD 55.00'),
        D({ font: '400 12.5px/1.75 ' + sans, color: '#3d3b36', marginTop: 7 }, 'Renews 21 Aug, automatically · started 4 March 2024 · 12-month term ends March 2026 · freeze used 1 of 3 months this year'),
        D({ display: 'flex', gap: 8, marginTop: 13, flexWrap: 'wrap' }, [
          prim('Renew', function () { v.act('sheet', 'ADM-MSH-01'); }),
          sec('Freeze', function () { v.act('sheet', 'ADM-MSH-03'); }),
          sec('Upgrade', function () { v.act('sheet', 'ADM-MSH-05'); }),
          sec('Cancel', function () { v.act('sheet', 'ADM-MSH-07'); })
        ])
      ]));
    } else {
      body = D({ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-start' }, [
        D({ flex: '1 1 440px', minWidth: 380 }, card(D({}, [
          D({ padding: '10px 14px', borderBottom: '1px solid ' + C.hair, font: '500 12.5px/1.3 ' + sans }, 'Timeline'),
          D({}, [
            ['06:12 today', C.err, 'Payment failed — card expired', 'Veyro · third attempt · INV-20418 · JOD 55.00'],
            ['06:13 today', '#a8a29a', 'Payment reminder drafted, not sent', 'Awaiting your approval'],
            ['31 Jul', C.info, 'PT session with Yousef · verified', '6th of 10 · lower body'],
            ['31 Jul', '#cbc6bc', 'Checked in · Khalda', '18:40 · last visit before the gap'],
            ['28 Jul', C.info, 'Health notes updated by Dr. Samar', 'Clinical content is not shown here'],
            ['12 Jul', '#a8a29a', 'Withdrew marketing consent', 'Service messages still allowed']
          ].map(function (r, i) {
            return D({ key: i, display: 'flex', gap: 11, padding: '11px 14px', borderTop: i ? '1px solid rgba(23,23,26,.06)' : 'none' }, [
              D({ width: 66, flexShrink: 0, font: '500 10.5px/1.4 ' + mono, color: C.t1 }, r[0]),
              D({ width: 2, background: r[1], flexShrink: 0, borderRadius: 1 }),
              D({ flex: 1, minWidth: 0 }, [D({ font: '450 12.5px/1.45 ' + sans }, r[2]), D({ font: '400 11.5px/1.55 ' + sans, color: C.t2, marginTop: 2 }, r[3])])
            ]);
          }))
        ]))),
        D({ flex: '1 1 260px', minWidth: 250, display: 'flex', flexDirection: 'column', gap: 14 }, [
          card(D({ padding: '13px 14px' }, [D({ font: '500 12px/1.3 ' + sans }, 'Coaching'), D({ font: '400 12px/1.7 ' + sans, color: '#3d3b36', marginTop: 7 }, 'Yousef Haddad · 4 of 10 credits · lower-body strength, week 8 of 12'), D({ font: '400 11px/1.55 ' + sans, color: C.t2, marginTop: 8 }, 'Operational context only. Programme detail lives in Coach.')])),
          card(D({ padding: '13px 14px' }, [D({ font: '500 12px/1.3 ' + sans }, 'Access'), D({ font: '400 12px/1.7 ' + sans, color: '#3d3b36', marginTop: 7 }, 'Card ···8841 active · app pass active · fingerprint enrolled'), D({ font: '400 11px/1.55 ' + sans, color: C.t2, marginTop: 8 }, 'Biometric data is never displayed or exportable.')]))
        ])
      ]);
    }
    return page([
      D({ background: C.surf, border: '1px solid ' + C.line, borderRadius: 4, padding: '16px 18px 0', margin: '-4px 0 0' }, [
        D({ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }, [
          D({ width: 52, height: 52, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
          D({ flex: 1, minWidth: 220 }, [
            D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [
              D({ font: '500 22px/1.2 ' + sans, letterSpacing: '-.016em' }, 'Ahmad Nabulsi'),
              badge('PAYMENT OVERDUE', C.err)
            ]),
            D({ font: '400 12px/1.55 ' + sans, color: C.t2, marginTop: 4 }, 'Club · Khalda · member since March 2024 · M-04188')
          ]),
          D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [
            prim('Take payment · JOD 55.00', function () { v.openScreen('POS-01'); }),
            sec('Message', function () { v.openScreen('ADM-COM-01'); })
          ])
        ]),
        D({ display: 'flex', marginTop: 14, flexWrap: 'wrap' }, tabs.map(function (t, i) {
          var on = v.tab360 === t;
          return Btn(function () { v.act('tab360', t); }, { key: i, font: (on ? '500' : '400') + ' 11.5px/1.4 ' + sans, color: on ? C.ink : C.t2, padding: '0 0 9px', borderBottom: on ? '1.5px solid ' + C.ink : '1.5px solid transparent', marginInlineEnd: 16 }, t);
        }))
      ]),
      v.tab360 === 'Overview' ? D({ display: 'flex', gap: 10, padding: '12px 14px', border: '1px solid ' + C.err, borderRadius: 4, background: C.surf, alignItems: 'flex-start' }, [
        D({ width: 3, alignSelf: 'stretch', background: C.err, flexShrink: 0 }),
        D({ flex: 1 }, [
          D({ font: '500 14px/1.35 ' + sans }, 'His card expired and JOD 55.00 is unpaid'),
          D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 3 }, 'Retried on the 17th and 18th. His access is unaffected — 14 days of grace, so he can train until 2 September.'),
          D({ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }, [prim('Send a payment link', function () { v.act('flash', 'Payment link sent by WhatsApp'); }), sec('Open the invoice', function () { v.openScreen('ADM-PAY-03'); })])
        ])
      ]) : null,
      body
    ]);
  };

  S['ADM-MSH-01'] = function (v) {
    return D({ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }, [
      D({ font: '500 17px/1.3 ' + sans }, 'Sell a membership'),
      D({}, [['Flex', 'Off-peak · no classes', '40.00', false], ['Club', 'All hours · classes included', '55.00', true], ['Club+', 'All clubs · 2 PT monthly', '78.00', false]].map(function (p, i) {
        return D({ key: i, border: p[3] ? '2px solid ' + C.ink : '1px solid rgba(23,23,26,.18)', borderRadius: 6, padding: '12px 13px', display: 'flex', gap: 11, alignItems: 'center', background: p[3] ? '#f7f9fc' : C.surf, marginTop: i ? 8 : 0 }, [
          D({ flex: 1 }, [D({ font: '450 14px/1.35 ' + sans }, p[0]), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, p[1])]),
          D({ font: '500 14px/1.2 ' + mono }, p[2])
        ]);
      })),
      D({ padding: '13px 14px', background: C.sunk, borderRadius: 4 }, [
        D({ display: 'flex', justifyContent: 'space-between' }, [D({ font: '400 12.5px/1.5 ' + sans, color: '#3d3b36' }, 'Today · pro-rata to 31 Aug'), D({ font: '500 12.5px/1.2 ' + mono }, 'JOD 21.29')]),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 5 }, [D({ font: '400 12.5px/1.5 ' + sans, color: '#3d3b36' }, 'Then monthly from 1 Sep'), D({ font: '500 12.5px/1.2 ' + mono }, 'JOD 55.00')]),
        D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(23,23,26,.08)' }, 'Monthly rolling — cancel any time with 30 days notice. No commitment fee.')
      ]),
      D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [prim('Take payment · 21.29', function () { v.act('flash', 'Membership active — receipt sent'); }), sec('Send a link', function () { v.act('flash', 'Payment link sent'); })])
    ]);
  };

  S['ADM-MSH-03'] = function (v) {
    return D({ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }, [
      D({ font: '500 17px/1.3 ' + sans }, 'Freeze this membership'),
      D({ padding: '13px 14px', background: C.sunk, borderRadius: 4, font: '400 12.5px/1.75 ' + sans, color: '#3d3b36' }, 'Billing pauses · access stops · the Club rate is held · end date moves out by the frozen period.'),
      D({ font: '400 12.5px/1.6 ' + sans, color: '#3d3b36' }, 'He has used 1 of 3 freeze months this year. Two remain.'),
      D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [prim('Freeze for one month', function () { v.act('flash', 'Frozen until 19 September — billing paused', true); }), sec('Choose dates', function () { v.act('flash', 'Date range picker'); })])
    ]);
  };

  S['ADM-MSH-05'] = function (v) {
    return D({ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }, [
      D({ font: '500 17px/1.3 ' + sans }, 'Upgrade to Club+'),
      D({ padding: '13px 14px', background: C.sunk, borderRadius: 4 }, [
        D({ display: 'flex', justifyContent: 'space-between' }, [D({ font: '400 12px/1.5 ' + sans, color: '#3d3b36' }, 'Club, 11 days remaining'), D({ font: '500 12px/1.2 ' + mono, color: C.ok }, '−20.17')]),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 4 }, [D({ font: '400 12px/1.5 ' + sans, color: '#3d3b36' }, 'Club+, 11 days'), D({ font: '500 12px/1.2 ' + mono }, '28.60')]),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 9, paddingTop: 9, borderTop: '1px solid rgba(23,23,26,.1)' }, [D({ font: '500 13px/1.4 ' + sans }, 'Pay today'), D({ font: '500 15px/1.2 ' + mono }, 'JOD 8.43')]),
        D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 7 }, 'From 1 Sep the monthly becomes JOD 78.00, up from 55.00.')
      ]),
      prim('Upgrade and charge 8.43', function () { v.act('flash', 'Upgraded to Club+ — all-clubs access active now', true); })
    ]);
  };

  S['ADM-MSH-07'] = function (v) {
    return D({ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }, [
      D({ font: '500 17px/1.3 ' + sans, color: C.err }, 'Cancel this membership'),
      D({ font: '400 12.5px/1.68 ' + sans, color: '#3d3b36' }, 'The 12-month commitment runs to March. Cancelling now triggers a two-month fee of JOD 110.00, and access ends on 18 September after the notice period.'),
      D({ padding: '12px 13px', border: '1px solid ' + C.ink, borderRadius: 4, background: '#f7f9fc' }, [
        D({ font: '500 11.5px/1.4 ' + sans, color: C.ink }, 'Before you cancel'),
        D({ font: '400 12px/1.6 ' + sans, color: '#3d3b36', marginTop: 4 }, 'He stopped visiting 19 days ago without giving a reason. A freeze costs him nothing and keeps the commitment intact.'),
        D({ marginTop: 9 }, sec('Offer a freeze instead', function () { v.act('sheet', 'ADM-MSH-03'); }))
      ]),
      D({}, [eyebrow('REASON · REQUIRED'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t3, border: '1px solid rgba(23,23,26,.2)', borderRadius: 6, padding: '10px 12px', marginTop: 6 }, 'Moving away, cost, unhappy, other…')]),
      D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [
        Btn(function () { v.act('flash', 'Cancellation recorded — access ends 18 September'); }, { font: '500 12.5px/1 ' + sans, background: C.err, color: C.surf, padding: '12px 14px', borderRadius: 6 }, 'Cancel membership'),
        sec('Keep it', function () { v.act('flash', 'No change made'); })
      ])
    ]);
  };

  S['ADM-CRM-01'] = function (v) {
    var cols = [['New', 12, [['Rana Sabbagh', 'open day · 2d', C.warn], ['Omar Zaid', 'instagram · 4h', C.t2]]], ['Contacted', 9, [['Lina Haddad', 'called · 1d', C.t2]]], ['Toured', 6, [['Faris Alami', 'Mon 17:00', C.t2]]], ['On trial', 7, [['Yara Nimri', 'day 6 of 7', C.warn]]], ['Joined', 11, []]];
    return page([
      D({ display: 'flex', gap: 14, alignItems: 'flex-end', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 250 }, h1('36 open leads · 7 going cold', v.loc + ' · 31% converted over 30 days, up 4 points')),
        prim('Add a lead', function () { v.act('flash', 'New lead — name and phone is enough'); })
      ]),
      D({ display: 'grid', gridTemplateColumns: 'repeat(5,minmax(0,1fr))', gap: 10 }, cols.map(function (c, i) {
        return card(D({}, [
          D({ padding: '9px 11px', borderBottom: '1px solid ' + C.hair, display: 'flex', gap: 6, alignItems: 'baseline' }, [D({ font: '500 11.5px/1.3 ' + sans, flex: 1 }, c[0]), D({ font: '500 11px/1.2 ' + mono, color: i === 4 ? C.ok : C.t2 }, String(c[1]))]),
          D({}, c[2].map(function (l, j) {
            return Btn(function () { v.openScreen(l[1].indexOf('day') === 0 || l[1].indexOf('day 6') >= 0 ? 'ADM-CRM-05' : 'ADM-CRM-03'); }, { key: j, padding: '9px 11px', borderTop: j ? '1px solid rgba(23,23,26,.06)' : 'none' }, [
              D({ font: '450 12px/1.35 ' + sans }, l[0]), D({ font: '400 10px/1.4 ' + mono, color: l[2], marginTop: 2 }, l[1])
            ]);
          })),
          c[1] > c[2].length ? D({ padding: '9px 11px', font: '400 10.5px/1.4 ' + mono, color: C.ink }, '+' + (c[1] - c[2].length) + ' more') : null
        ]), { key: i });
      })),
      card(D({ padding: '14px 16px' }, [
        D({ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }, [
          D({ width: 44, height: 44, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
          D({ flex: 1, minWidth: 220 }, [
            D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [D({ font: '500 19px/1.25 ' + sans }, 'Rana Sabbagh'), badge('NO CONTACT · 2 DAYS', C.warn)]),
            D({ font: '400 12px/1.55 ' + sans, color: C.t2, marginTop: 3 }, 'Sweifieh open day · +962 79 411 0288 · interested in classes and PT')
          ]),
          D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [prim('Start a 7-day trial', function () { v.openScreen('ADM-CRM-05'); }), sec('WhatsApp', function () { v.openScreen('ADM-COM-01'); })])
        ]),
        D({ marginTop: 14, border: '1px solid ' + C.ai, borderRadius: 4, overflow: 'hidden' }, [
          D({ padding: '8px 13px', background: C.aiWash, display: 'flex', gap: 7, alignItems: 'center' }, [D({ font: '400 10.5px/1 ' + mono, color: C.ai }, '✦'), D({ font: '500 10px/1.4 ' + mono, color: C.ai, letterSpacing: '.06em' }, 'VEYRO SUGGESTS · YOU SEND IT')]),
          D({ padding: '12px 13px' }, D({ font: '400 13px/1.68 ' + sans, color: '#2c2a26' }, 'She asked about the 19:00 spin class twice at the open day. Offer the trial with a spin booking already held — 4 of the 11 who joined this month came in through a class, not a tour.'))
        ])
      ]))
    ]);
  };

  S['ADM-CRM-05'] = function (v) {
    return page([
      h1('Rana Sabbagh · trial day 6 of 7', 'ADM-CRM-05 · Khalda · started 13 August'),
      metrics([['VISITS', '4', 'of 7 days'], ['CLASSES', '3', 'all spin'], ['TRIAL ENDS', 'tomorrow', '20 August'], ['CONVERSION LIKELIHOOD', 'High', 'class-led, 4 visits']]),
      card(D({ padding: '15px 17px' }, [
        D({ font: '500 15px/1.35 ' + sans }, 'Her trial ends tomorrow'),
        D({ font: '400 12.5px/1.68 ' + sans, color: '#3d3b36', marginTop: 5 }, 'Four visits and three spin classes in six days. Members who attend three or more classes on trial convert at 68% here. Club is the fit — Flex would exclude the classes she actually came for.'),
        D({ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }, [
          prim('Convert to Club', function () { v.openScreen('ADM-CRM-06'); }),
          sec('Extend the trial 3 days', function () { v.act('flash', 'Trial extended to 23 August'); }),
          ghost('Mark lost', function () { v.act('flash', 'Reason required before marking lost'); })
        ])
      ]))
    ]);
  };

  S['ADM-CRM-06'] = function (v) {
    return page([
      h1('Convert Rana to a member', 'ADM-CRM-06 · the trial record becomes the membership — nothing is re-entered'),
      card(D({ padding: '16px 18px' }, [
        eyebrow('CARRIED FORWARD FROM HER TRIAL'),
        D({ font: '400 13px/1.75 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Name, phone, waiver acceptance, emergency contact, her 4 check-ins, her 3 spin bookings, and the note from the open day. Same record ID — M-04913 was issued when the trial started.'),
        D({ height: 1, background: 'rgba(23,23,26,.1)', margin: '14px 0' }),
        eyebrow('WHAT YOU CHOOSE NOW'),
        D({ font: '400 13px/1.75 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Plan, term, start date, payment method. Four fields.'),
        D({ display: 'flex', gap: 8, marginTop: 13, flexWrap: 'wrap' }, [
          prim('Club · monthly · JOD 55.00', function () { v.act('flash', 'Rana is a member — welcome flow sent'); }),
          sec('Open the sale sheet', function () { v.act('sheet', 'ADM-MSH-01'); })
        ])
      ])),
      D({ font: '400 12px/1.6 ' + sans, color: C.t2, maxWidth: '80ch' }, 'This is the duplicate-data-entry fix from the Phase 6 review, made structural: a lead, a trialist and a member are one record at three stages.')
    ]);
  };

  S['ADM-PAY-01'] = function (v) {
    return page([
      h1('Payments', v.loc + ' · August · JOD 41,280 collected · 6 failed'),
      metrics([['COLLECTED', 'JOD 41,280', 'month to date'], ['FAILED', 'JOD 312.00', '6 payments'], ['REFUNDED', 'JOD 165.00', '3 this month'], ['PENDING', 'JOD 88.00', '2 CliQ transfers']]),
      card(D({ overflowX: 'auto' }, D({ minWidth: 880 }, [
        D({ display: 'grid', gridTemplateColumns: '110px minmax(0,1.2fr) 100px 96px 100px minmax(0,1fr)', gap: 12, padding: '9px 16px', background: C.sunk, borderBottom: '1px solid ' + C.hair, font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, ['INVOICE', 'MEMBER', 'AMOUNT', 'METHOD', 'STATE', 'JOFOTARA'].map(function (x, i) { return D({ key: i }, x); })),
        D({}, [
          ['INV-20418', 'Ahmad Nabulsi', 'JOD 55.00', 'Visa ···4417', 'FAILED', C.err, 'not submitted'],
          ['INV-20417', 'Dana Qasem', 'JOD 45.00', 'Visa ···9012', 'FAILED', C.err, 'not submitted'],
          ['INV-20416', 'Lina Haddad', 'JOD 78.00', 'CliQ', 'PAID', C.ok, 'submitted'],
          ['INV-20415', 'Omar Zaid', 'JOD 55.00', 'Cash', 'PAID', C.ok, 'submitted'],
          ['INV-20414', 'Nour Khoury', 'JOD 40.00', 'Visa ···1188', 'PAID', C.ok, 'REJECTED'],
          ['INV-20413', 'Faris Alami', 'JOD 45.00', 'Visa ···3301', 'FAILED', C.err, 'not submitted']
        ].map(function (r, i) {
          return Btn(function () { v.openScreen('ADM-PAY-03'); }, { key: i, display: 'grid', gridTemplateColumns: '110px minmax(0,1.2fr) 100px 96px 100px minmax(0,1fr)', gap: 12, padding: '0 16px', height: 34, alignItems: 'center', borderBottom: '1px solid rgba(23,23,26,.06)' }, [
            D({ font: '400 11px/1.3 ' + mono }, r[0]), D({ font: '450 12px/1.3 ' + sans }, r[1]),
            D({ font: '500 11.5px/1.2 ' + mono, color: r[5] === C.err ? C.err : C.t1 }, r[2]),
            D({ font: '400 11px/1.3 ' + mono, color: C.t2 }, r[3]),
            D({ font: '500 10px/1.4 ' + mono, color: r[5] }, r[4]),
            D({ font: '400 10.5px/1.3 ' + mono, color: r[6] === 'REJECTED' ? C.err : C.t2 }, r[6])
          ]);
        }))
      ]))),
      D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [prim('Open the recovery workspace', function () { v.openScreen('ADM-PAY-05'); }), sec('Fix the rejected e-invoice', function () { v.openScreen('ADM-SET-03'); })])
    ]);
  };

  S['ADM-PAY-03'] = function (v) {
    return page([
      D({ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 230 }, [
          D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [D({ font: '500 19px/1.2 ' + mono }, 'INV-20418'), badge('UNPAID · 2 DAYS LATE', C.err)]),
          D({ font: '400 12px/1.5 ' + sans, color: C.t2, marginTop: 4 }, 'Ahmad Nabulsi · issued 17 Aug · due 17 Aug · Khalda')
        ]),
        prim('Take payment', function () { v.openScreen('POS-01'); })
      ]),
      card(D({ padding: '16px 18px' }, [
        D({ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 74px 96px', gap: 12, paddingBottom: 8, borderBottom: '1px solid rgba(23,23,26,.1)', font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, [D({}, 'DESCRIPTION'), D({}, 'QTY'), D({}, 'AMOUNT')]),
        D({ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 74px 96px', gap: 12, padding: '11px 0', borderBottom: '1px solid rgba(23,23,26,.06)', alignItems: 'baseline' }, [
          D({}, [D({ font: '450 13px/1.4 ' + sans }, 'Club membership · August'), D({ font: '400 11px/1.4 ' + mono, color: C.t2, marginTop: 2 }, '1–31 Aug · monthly rolling · tax exempt')]),
          D({ font: '400 12px/1.3 ' + mono, color: C.t2 }, '1'), D({ font: '500 13px/1.2 ' + mono }, '55.00')
        ]),
        D({ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 74px 96px', gap: 12, paddingTop: 12, alignItems: 'baseline' }, [D({ font: '500 14px/1.4 ' + sans }, 'Total'), D({}), D({ font: '500 18px/1.15 ' + mono }, 'JOD 55.00')]),
        D({ marginTop: 16, paddingTop: 14, borderTop: '1px solid rgba(23,23,26,.1)' }, [
          eyebrow('WHAT HAS HAPPENED TO THIS INVOICE'),
          D({ marginTop: 9 }, [['17 Aug 06:00', 'Issued and charged automatically', C.t1], ['17 Aug 06:01', 'Declined · card expired · Visa ···4417', C.err], ['18 Aug 06:00', 'Retry 1 declined · same reason', C.err], ['19 Aug 06:12', 'Retry 2 declined · dunning stopped', C.err], ['19 Aug 06:13', 'Reminder drafted, awaiting approval', C.t1]].map(function (r, i) {
            return D({ key: i, display: 'flex', gap: 11, padding: '8px 0', borderBottom: i < 4 ? '1px solid rgba(23,23,26,.05)' : 'none' }, [
              D({ font: '400 10.5px/1.4 ' + mono, color: C.t2, width: 84, flexShrink: 0 }, r[0]),
              D({ font: '400 12px/1.45 ' + sans, flex: 1, color: r[2] }, r[1])
            ]);
          }))
        ]),
        D({ marginTop: 14, padding: '12px 13px', border: '1px solid ' + C.warn, borderRadius: 4 }, [
          D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [badge('JOFOTARA', C.warn), D({ font: '450 12.5px/1.4 ' + sans, flex: 1, minWidth: 180 }, 'Not submitted — e-invoices are sent on payment, not issue')]),
          D({ font: '400 11.5px/1.55 ' + sans, color: C.t2, marginTop: 6 }, 'Jordan requires submission of the settled transaction. An unpaid invoice has nothing to report yet, so this state is correct rather than a failure.')
        ]),
        D({ marginTop: 14, font: '400 12px/1.6 ' + sans, color: C.t2 }, 'There is no edit affordance on this screen at any permission level. Corrections are credit notes with their own number — which is why this timeline can be trusted as an audit trail.')
      ]))
    ]);
  };

  S['ADM-PAY-05'] = function (v) {
    var done = v.resolvedIds.indexOf('pay') >= 0;
    var rows = [['Ahmad Nabulsi', 'Card expired · Visa ···4417', 'JOD 55.00', 'link ready'], ['Dana Qasem', 'Insufficient funds', 'JOD 45.00', 'link ready'], ['Yara Mansour', 'Card expired · frozen member', 'JOD 72.00', 'review first'], ['Tareq Odeh', 'Card expired · membership ended', 'JOD 40.00', 'review first'], ['Hala Barakat', 'Card expired · Visa ···2201', 'JOD 55.00', 'link ready'], ['Faris Alami', 'Insufficient funds', 'JOD 45.00', 'link ready']];
    return page([
      D({ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 240 }, h1(done ? 'Links sent to all 6' : '6 failed payments · JOD 312.00', done ? 'Sent 2 minutes ago · awaiting payment' : 'All retries exhausted · no access blocked')),
        done ? sec('Back to Command Center', function () { v.openScreen('ADM-CC-01'); }) : prim('Send all 6 links', function () { v.act('resolve', 'pay'); })
      ]),
      card(D({}, rows.map(function (r, i) {
        return D({ key: i, padding: '10px 15px', borderTop: i ? '1px solid rgba(23,23,26,.06)' : 'none', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }, [
          D({ font: '400 11px/1 ' + mono, color: done ? C.ok : C.ink, width: 14 }, done ? '✓' : '☑'),
          D({ flex: 1, minWidth: 160 }, [D({ font: '450 12.5px/1.35 ' + sans }, r[0]), D({ font: '400 10.5px/1.4 ' + mono, color: C.t2, marginTop: 2 }, r[1])]),
          D({ font: '500 12px/1.2 ' + mono, color: C.err }, r[2]),
          D({ font: '400 10.5px/1.4 ' + mono, color: done ? C.ok : (r[3] === 'review first' ? C.warn : C.t2), width: 108, textAlign: 'end' }, done ? 'link sent' : r[3])
        ]);
      }))),
      card(D({ padding: '14px 16px' }, [
        D({ font: '500 11.5px/1.4 ' + sans }, 'The message they receive'),
        D({ font: '400 12.5px/1.7 ' + sans, color: '#3d3b36', marginTop: 6, padding: '10px 12px', background: C.surf, border: '1px solid rgba(23,23,26,.1)', borderRadius: 4 }, "Hi Ahmad — your August payment of JOD 55.00 didn't go through because your card expired. You can pay here: veyro.link/p/8k2m. You're still able to train as normal."),
        D({ font: '400 11.5px/1.55 ' + sans, color: C.t2, marginTop: 8 }, 'Sent in each member’s chosen language. Two of the six have withdrawn marketing consent — this is a service message, so it still sends, and the distinction is enforced by the system rather than left to the sender.')
      ]))
    ]);
  };

  S['ADM-AI-01'] = function (v) {
    return page([
      D({ border: '1px solid ' + C.ai, borderRadius: 4, background: C.surf, overflow: 'hidden' }, [
        D({ padding: '10px 15px', background: C.aiWash, display: 'flex', gap: 8, alignItems: 'center' }, [D({ font: '400 10.5px/1 ' + mono, color: C.ai }, '✦'), D({ font: '500 10px/1.4 ' + mono, color: C.ai, letterSpacing: '.07em' }, 'HOW VEYRO REACHED THIS · ADM-AI-01')]),
        D({ padding: '16px 18px' }, [
          eyebrow('SYSTEM FACT'),
          D({ font: '450 15px/1.6 ' + sans, marginTop: 6 }, 'Collections are JOD 3,490 below the same point in July — 41,280 against 44,770.'),
          D({ height: 1, background: 'rgba(23,23,26,.1)', margin: '14px 0' }),
          eyebrow('DERIVATION', C.ai),
          D({ marginTop: 8 }, [
            ['−1,840', 'PT revenue at Khalda. Omar’s roster fell from 14 to 9 when he cut his hours, and 31 delivered sessions were never verified, so they were never billed.', 'ADM-SCH-05'],
            ['−1,120', 'Annual renewals. Seven fewer than July; six of those seven switched to monthly rather than leaving.', 'ADM-MEM-05'],
            ['−530', 'Failed payments not yet recovered, including this morning’s six.', 'ADM-PAY-05']
          ].map(function (r, i) {
            return D({ key: i, display: 'flex', gap: 10, alignItems: 'baseline', padding: '9px 0', borderTop: i ? '1px solid rgba(23,23,26,.06)' : 'none' }, [
              D({ font: '500 12.5px/1.4 ' + mono, width: 62, textAlign: 'end', flexShrink: 0 }, r[0]),
              D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', flex: 1 }, r[1]),
              Btn(function () { v.openScreen(r[2]); }, { font: '400 11px/1.4 ' + mono, color: C.ai, flexShrink: 0 }, 'evidence ↗')
            ]);
          })),
          D({ marginTop: 12, padding: '12px 13px', background: C.sunk, borderRadius: 4, font: '400 12.5px/1.68 ' + sans, color: '#3d3b36' }, 'Confident on the session gap and the renewals — both come straight from records. Less confident that the roster change caused the PT drop; Omar’s remaining clients also booked less often.'),
          D({ height: 1, background: 'rgba(23,23,26,.1)', margin: '14px 0' }),
          eyebrow('RECOMMENDED · YOU CONFIRM BEFORE ANYTHING RUNS', C.ai),
          D({ font: '450 13.5px/1.55 ' + sans, marginTop: 6 }, 'Ask Khalda to verify the 31 open sessions. If they are genuine, that alone recovers about JOD 1,240.'),
          D({ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }, [prim('Preview the request', function () { v.act('flash', 'Request drafted — nothing sent until you confirm'); }), sec('Open the 31 sessions', function () { v.openScreen('ADM-SCH-05'); })]),
          D({ font: '400 10.5px/1.5 ' + mono, color: C.t4, marginTop: 10 }, 'Read from payments, PT sessions and rosters · 1–19 Aug · generated 08:38')
        ])
      ])
    ]);
  };

  S['ADM-SCH-01'] = function (v) {
    var days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    var times = ['07:00', '09:00', '12:00', '17:00', '19:00'];
    return page([
      h1('Schedule', v.loc + ' · week of 18 August · 63 classes · 1 without a coach'),
      card(D({ overflowX: 'auto' }, D({ minWidth: 860 }, [
        D({ display: 'grid', gridTemplateColumns: '64px repeat(7,minmax(0,1fr))', gap: 1, background: 'rgba(23,23,26,.1)' },
          [D({ style: {} }, '')].concat(days.map(function (d, i) { return D({ key: i, background: C.sunk, padding: '8px 10px', font: '500 10px/1.4 ' + mono, color: C.t2 }, d); }))),
        D({}, times.map(function (t, ri) {
          return D({ key: ri, display: 'grid', gridTemplateColumns: '64px repeat(7,minmax(0,1fr))', gap: 1, background: 'rgba(23,23,26,.08)' },
            [D({ background: C.sunk, padding: '10px', font: '400 10px/1.4 ' + mono, color: C.t2 }, t)].concat(days.map(function (d, ci) {
              var isGap = t === '19:00' && d === 'Thu';
              var has = (ri + ci) % 3 !== 2;
              return has ? Btn(function () { v.openScreen('ADM-SCH-02'); }, { key: ci, background: C.surf, padding: '8px 9px', borderInlineStart: isGap ? '2px solid ' + C.warn : '2px solid transparent' }, [
                D({ font: '450 11px/1.35 ' + sans }, ['Spin', 'Yoga', 'HIIT', 'Pilates'][(ri + ci) % 4]),
                D({ font: '400 9.5px/1.4 ' + mono, color: isGap ? C.warn : C.t2, marginTop: 2 }, isGap ? 'no coach' : ['Dana', 'Yousef', 'Omar'][(ri + ci) % 3])
              ]) : D({ key: ci, background: C.canvas });
            })));
        }))
      ]))),
      D({ font: '400 12px/1.6 ' + sans, color: C.t2, maxWidth: '84ch' }, 'Only the one class needing a coach carries colour. Fifty-four healthy cells competing for attention would bury it — that was a P1 finding in the Phase 9 audit.')
    ]);
  };

  S['ADM-SCH-02'] = function (v) {
    return page([
      D({ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 220 }, [
          D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [D({ font: '500 22px/1.2 ' + sans, letterSpacing: '-.016em' }, 'Spin · Thursday 19:00'), badge('NO COACH', C.warn)]),
          D({ font: '400 12px/1.5 ' + sans, color: C.t2, marginTop: 4 }, 'Studio 2 · 20 bikes · Khalda')
        ])
      ]),
      metrics([['BOOKED', '18', 'of 20 bikes'], ['FREE', '2', 'still bookable'], ['WAITLIST', '3', 'auto-promote on'], ['USUAL FILL', '92%', 'Thursday spin']]),
      card(D({}, [
        D({ padding: '9px 14px', background: C.sunk, borderBottom: '1px solid ' + C.hair }, eyebrow('BOOKED · 18')),
        D({}, [['Dana Qasem', 'booked 6d ago', ''], ['Hala Barakat', 'booked 4d ago', '2 no-shows'], ['Lina Haddad', 'booked 2d ago', ''], ['Nour Khoury', 'booked yesterday', ''], ['Rana Sabbagh', 'trial member', '']].map(function (r, i) {
          return D({ key: i, padding: '9px 14px', borderTop: i ? '1px solid rgba(23,23,26,.06)' : 'none', display: 'flex', gap: 9, alignItems: 'center' }, [
            D({ width: 22, height: 22, borderRadius: '50%', background: '#ece9e3', flexShrink: 0 }),
            D({ font: '450 12px/1.3 ' + sans, flex: 1 }, r[0]),
            D({ font: '400 10px/1.4 ' + mono, color: r[2] ? C.warn : C.t2 }, r[2] || r[1])
          ]);
        })),
        D({ padding: '9px 14px', borderTop: '1px solid ' + C.hair, font: '400 11.5px/1.4 ' + sans, color: C.ink }, 'Show 13 more')
      ])),
      D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [
        prim('Assign Dana', function () { v.act('flash', 'Dana offered the class — she is notified now'); }),
        sec('Message the 18', function () { v.openScreen('ADM-COM-03'); }),
        Btn(function () { v.act('flash', 'Cancelling requires a message and a credit or transfer for each member'); }, { font: '500 12px/1 ' + sans, border: '1px solid rgba(138,59,31,.4)', color: C.err, padding: '10px 12px', borderRadius: 6 }, 'Cancel class')
      ])
    ]);
  };

  S['ADM-SRCH-01'] = function (v) {
    return page([
      h1('Command palette', 'ADM-SRCH-01 · press ⌘K anywhere in Admin'),
      card(D({ padding: '16px 18px' }, [
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', maxWidth: '80ch' }, 'One entry point for members, leads, staff, invoices, bookings, screens, commands and questions for Veyro. Results are filtered at query time by your role and location scope — a receptionist searching “refund” finds nothing here, by design.'),
        D({ marginTop: 13 }, prim('Open it now', function () { v.act('flash', 'Press ⌘K — the palette is live on every Admin screen'); }))
      ]))
    ]);
  };

  // ---- Front desk & POS ----
  S['FD-01'] = function (v) {
    return page([
      D({ border: '2px solid ' + C.ink, borderRadius: 6, background: C.surf, padding: '16px 18px' }, [
        eyebrow('SCAN OR TYPE · FOCUS IS HERE', C.ink),
        D({ display: 'flex', gap: 11, alignItems: 'center', marginTop: 10 }, [
          D({ flex: 1, font: '400 19px/1.3 ' + sans, color: C.t3, borderBottom: '1px solid rgba(23,23,26,.16)', paddingBottom: 9 }, 'Card, phone, or name'),
          sec('Guest', function () { v.act('flash', 'Guest entry — waiver required'); }, true)
        ]),
        D({ font: '400 11.5px/1.5 ' + mono, color: C.t2, marginTop: 9 }, 'Turnstile and app check-ins appear below automatically · no action needed')
      ]),
      card(D({}, [
        D({ padding: '11px 16px', borderBottom: '1px solid ' + C.hair, display: 'flex', gap: 9, alignItems: 'baseline' }, [D({ font: '500 13.5px/1.3 ' + sans, flex: 1 }, 'Just now'), D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, 'live · last 10 minutes')]),
        D({ display: 'flex' }, [
          D({ width: 3, background: C.warn, flexShrink: 0 }),
          D({ flex: 1, padding: '14px 16px' }, [
            D({ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
              D({ width: 40, height: 40, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
              D({ flex: 1, minWidth: 180 }, [D({ font: '500 17px/1.3 ' + sans }, 'Ahmad Nabulsi'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, 'Club · card ···8841 · 18:42')]),
              badge('OWES JOD 55.00', C.warn)
            ]),
            D({ font: '400 13.5px/1.62 ' + sans, color: '#2c2a26', marginTop: 10, background: C.sunk, padding: '11px 13px', borderRadius: 4 }, 'Let him in. His card expired and he owes 55 dinars — mention it warmly, offer to settle now. He can train until 2 September either way.'),
            D({ display: 'flex', gap: 9, marginTop: 12, flexWrap: 'wrap' }, [
              prim('Take JOD 55.00', function () { v.openScreen('POS-01'); }, true),
              sec('Send link instead', function () { v.act('flash', 'Payment link sent by WhatsApp'); }, true),
              ghost('Mentioned it', function () { v.act('flash', 'Noted — cleared from the queue'); })
            ])
          ])
        ]),
        D({ display: 'flex', borderTop: '1px solid ' + C.hair }, [
          D({ width: 3, background: C.err, flexShrink: 0 }),
          D({ flex: 1, padding: '14px 16px' }, [
            D({ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
              D({ width: 40, height: 40, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
              D({ flex: 1, minWidth: 180 }, [D({ font: '500 17px/1.3 ' + sans }, 'Tareq Odeh'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, 'Flex · app pass · 18:39')]),
              badge('EXPIRED 12 DAYS AGO', C.err)
            ]),
            D({ marginTop: 12 }, prim('Resolve this', function () { v.openScreen('FD-03'); }, true))
          ])
        ]),
        [['Dana Qasem', 'Club+ · turnstile · 18:41'], ['Hala Barakat', 'Club · app · 18:40']].map(function (r, i) {
          return D({ key: i, display: 'flex', borderTop: '1px solid ' + C.hair, background: C.sunk }, [
            D({ width: 3, background: '#cbc6bc', flexShrink: 0 }),
            D({ flex: 1, padding: '11px 16px', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
              D({ width: 30, height: 30, borderRadius: '50%', background: '#ece9e3', flexShrink: 0 }),
              D({ font: '450 14px/1.3 ' + sans, flex: 1, minWidth: 140 }, r[0]),
              D({ font: '400 12px/1.4 ' + mono, color: C.t2 }, r[1]),
              D({ font: '500 11px/1.4 ' + mono, color: C.ok }, 'IN')
            ])
          ]);
        }),
        D({ padding: '10px 16px', borderTop: '1px solid ' + C.hair, font: '400 12px/1.5 ' + sans, color: C.t2 }, 'Clean check-ins clear themselves after 10 minutes. Only the two above need you.')
      ]))
    ]);
  };

  S['FD-03'] = function (v) {
    return page([
      h1('Tareq Odeh cannot get in', 'FD-03 · Flex membership ended 7 August · grace ran out 5 days ago'),
      card(D({ padding: '16px 18px' }, [
        D({ font: '400 13.5px/1.68 ' + sans, color: '#2c2a26', maxWidth: '80ch' }, 'He was here three times a week for two years and then stopped. Worth asking whether something changed rather than leading with the renewal — but he is standing at the desk now, so give him a way in either way.'),
        D({ display: 'flex', gap: 9, marginTop: 14, flexWrap: 'wrap' }, [
          prim('Renew · Flex JOD 40.00', function () { v.openScreen('POS-04'); }, true),
          sec('One-day pass · 8.00', function () { v.openScreen('POS-01'); }, true),
          sec('Let in, flag for a call', function () { v.act('flash', 'Entry allowed once — flagged for the sales team'); }, true)
        ]),
        D({ font: '400 12px/1.6 ' + sans, color: C.t2, marginTop: 14 }, v.role === 'Reception' ? 'You have override authority for a single entry. Anything longer needs Ziad.' : 'As ' + v.role + ' you can also waive the lapse — recorded with your name and a reason.')
      ]))
    ]);
  };

  S['POS-01'] = function (v) {
    var sub = v.cart.reduce(function (a, x) { return a + x[1] * x[2]; }, 0);
    var taxable = v.cart.filter(function (x) { return x[0].indexOf('membership') < 0; }).reduce(function (a, x) { return a + x[1] * x[2]; }, 0);
    var disc = v.discount ? sub * v.discount / 100 : 0;
    var tax = (taxable - (v.discount ? taxable * v.discount / 100 : 0)) * 0.16;
    var total = sub - disc + tax;
    var f2 = function (n) { return n.toFixed(2); };
    var products = [['Water 500ml', 0.5], ['Protein bar', 2], ['Shaker', 6], ['Towel hire', 1], ['Whey 1kg', 28], ['Day pass', 8]];
    if (v.payState === 'approved') {
      return page([
        D({ border: '1px solid ' + C.ok, borderRadius: 6, overflow: 'hidden' }, [
          D({ padding: '10px 15px', background: C.ok, font: '500 10px/1.4 ' + mono, color: C.surf, letterSpacing: '.07em' }, 'PAID'),
          D({ padding: '18px 20px', background: C.surf }, [
            D({ font: '500 24px/1.15 ' + mono }, 'JOD ' + f2(total)),
            D({ font: '400 13px/1.65 ' + sans, color: '#3d3b36', marginTop: 8 }, 'Card ···4417 · receipt sent by WhatsApp · e-invoice submitted to JoFotara'),
            D({ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }, [sec('Print', function () { v.openScreen('POS-07'); }, true), prim('Next sale', function () { v.act('payReset'); }, true)]),
            D({ font: '400 11.5px/1.55 ' + sans, color: C.t2, marginTop: 12 }, 'Focus is already back in the scan field. Nothing to dismiss — the panel clears when the next card scans.')
          ])
        ])
      ]);
    }
    return page([
      D({ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
        D({ font: '500 20px/1.2 ' + sans, letterSpacing: '-.015em', flex: 1, minWidth: 200 }, 'Sale · Ahmad Nabulsi'),
        D({ font: '400 11.5px/1.4 ' + mono, color: C.t2 }, 'Club · wallet JOD 12.50')
      ]),
      D({ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }, [
        D({ flex: '1 1 380px', minWidth: 340 }, card(D({ padding: '14px 16px' }, [
          D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(108px,1fr))', gap: 9 }, products.map(function (p, i) {
            return Btn(function () { v.act('addItem', p); }, { key: i, border: '1px solid rgba(23,23,26,.18)', borderRadius: 6, padding: '13px 11px', textAlign: 'center', background: C.sunk }, [
              D({ font: '450 13px/1.35 ' + sans }, p[0]), D({ font: '500 13px/1.2 ' + mono, marginTop: 6 }, f2(p[1]))
            ]);
          }).concat([D({ key: 'x', border: '1px solid rgba(23,23,26,.18)', borderRadius: 6, padding: '13px 11px', textAlign: 'center', background: C.sunk, opacity: .55 }, [D({ font: '450 13px/1.35 ' + sans }, 'Creatine'), D({ font: '500 11px/1.2 ' + mono, color: C.warn, marginTop: 6 }, 'out of stock')])]))
        ]))),
        D({ flex: '0 1 280px', minWidth: 260 }, card(D({ padding: '14px 16px' }, [
          eyebrow('CART · ' + v.cart.length + ' ITEMS'),
          D({ marginTop: 11 }, v.cart.map(function (x, i) {
            return D({ key: i, display: 'flex', gap: 8, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid rgba(23,23,26,.06)' }, [
              Btn(function () { v.act('qty', [x[0], -1]); }, { font: '400 12px/1 ' + mono, color: C.t2, width: 14 }, '−'),
              D({ font: '400 11px/1.4 ' + mono, color: C.t2, width: 20 }, x[1] + '×'),
              D({ font: '450 12.5px/1.4 ' + sans, flex: 1 }, x[0]),
              D({ font: '500 12px/1.2 ' + mono }, f2(x[1] * x[2]))
            ]);
          })),
          D({ marginTop: 12, paddingTop: 11, borderTop: '1px solid ' + C.line }, [
            D({ display: 'flex', justifyContent: 'space-between' }, [D({ font: '400 12px/1.4 ' + sans, color: C.t2 }, 'Subtotal'), D({ font: '500 12px/1.2 ' + mono }, f2(sub))]),
            v.discount ? D({ display: 'flex', justifyContent: 'space-between', marginTop: 5 }, [D({ font: '400 12px/1.4 ' + sans, color: C.t2 }, 'Discount ' + v.discount + '%'), D({ font: '500 12px/1.2 ' + mono, color: C.ok }, '−' + f2(disc))]) : null,
            D({ display: 'flex', justifyContent: 'space-between', marginTop: 5 }, [D({ font: '400 12px/1.4 ' + sans, color: C.t2 }, 'Sales tax 16%'), D({ font: '500 12px/1.2 ' + mono }, f2(tax))]),
            D({ display: 'flex', justifyContent: 'space-between', marginTop: 9, paddingTop: 9, borderTop: '1px solid rgba(23,23,26,.1)' }, [D({ font: '500 14px/1.3 ' + sans }, 'Total'), D({ font: '500 19px/1.15 ' + mono }, f2(total))]),
            D({ font: '400 10.5px/1.5 ' + mono, color: C.t2, marginTop: 5 }, 'Tax on retail only · membership exempt')
          ]),
          D({ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }, [
            prim('Card', function () { v.openScreen('POS-02'); }, true),
            D({ display: 'flex', gap: 8 }, [
              D({ flex: 1 }, sec('Cash', function () { v.act('pay', 'approved'); }, true)),
              D({ flex: 1 }, sec('Split', function () { v.openScreen('POS-03'); }, true))
            ]),
            v.role === 'Reception' && !v.discount
              ? ghost('Discount · needs manager', function () { v.act('flash', 'Discount over 10% needs Ziad — a different person, not a louder dialog'); })
              : (v.discount ? ghost('Clear discount', function () { v.act('discount', 0); }) : ghost('Apply 10% discount', function () { v.act('discount', 10); }))
          ])
        ])))
      ])
    ]);
  };

  S['POS-02'] = function (v) {
    var states = {
      idle: ['WAITING FOR THE CARD', C.ink, C.wash, C.ink, 'Present card', 'Terminal is ready. Tap, insert or swipe.', 'No timeout is shown to the member — a countdown makes people fumble.', [['Simulate approval', function () { v.act('pay', 'approved'); }], ['Simulate decline', function () { v.act('pay', 'declined'); }], ['Simulate offline', function () { v.act('pay', 'offline'); }]]],
      waiting: ['PROCESSING', C.t2, C.sunk, C.t2, 'Authorising', 'Do not remove the card. This usually takes about five seconds.', 'No cancel here — an interrupted authorisation is the one state that produces a double charge. The button is absent, not disabled.', []],
      approved: ['APPROVED', C.ok, C.ok, C.surf, 'Paid', 'Card ···4417 · receipt sent by WhatsApp · e-invoice submitted.', 'Focus returns to the scan field immediately.', [['Receipt', function () { v.openScreen('POS-07'); }], ['Next sale', function () { v.act('payReset'); }]]],
      declined: ['DECLINED', C.err, C.err, C.surf, 'Declined', 'The bank declined this card. Nothing has been charged. Ask for another card, or take cash.', 'Names what happened and confirms no money moved — never a bank error code.', [['Try another card', function () { v.act('payReset'); }], ['Take cash instead', function () { v.act('pay', 'approved'); }]]],
      offline: ['TERMINAL UNREACHABLE', C.warn, C.warn, C.surf, 'Queue this payment', 'The card reader is not responding. Cash and CliQ still work normally.', 'Queuing records the sale as PAYMENT PENDING and prints a receipt saying so. It never says paid.', [['Queue this payment', function () { v.act('flash', 'Queued — receipt says PAYMENT PENDING'); }], ['Take cash instead', function () { v.act('pay', 'approved'); }]]]
    };
    var s = states[v.payState] || states.idle;
    return page([
      h1('Card terminal', 'POS-02 · six states · JOD 60.72'),
      D({ border: '1px solid ' + s[1], borderRadius: 6, background: C.surf, overflow: 'hidden', maxWidth: 520 }, [
        D({ padding: '9px 15px', background: s[2], font: '500 9.5px/1.4 ' + mono, color: s[3], letterSpacing: '.07em' }, s[0]),
        D({ padding: '18px 20px' }, [
          D({ font: '500 17px/1.3 ' + sans }, s[4]),
          D({ font: '500 26px/1.15 ' + mono, marginTop: 10, color: s[1] === C.t2 ? C.t1 : s[1] }, 'JOD 60.72'),
          D({ font: '400 13px/1.65 ' + sans, color: '#3d3b36', marginTop: 10 }, s[5]),
          s[7].length ? D({ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }, s[7].map(function (b, i) { return i === 0 ? prim(b[0], b[1], true) : sec(b[0], b[1], true); })) : null,
          D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 12, paddingTop: 11, borderTop: '1px solid rgba(23,23,26,.08)' }, s[6])
        ])
      ])
    ]);
  };

  S['POS-03'] = function (v) {
    var total = 60.72;
    var taken = v.splitTaken.reduce(function (a, x) { return a + x[1]; }, 0);
    var left = Math.max(0, total - taken);
    return page([
      h1('Split payment', 'POS-03 · nothing settles until the split completes'),
      card(D({ padding: '16px 18px', maxWidth: 460 }, [
        D({ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }, [D({ font: '500 15px/1.4 ' + sans }, 'Total due'), D({ font: '500 22px/1.15 ' + mono }, 'JOD ' + total.toFixed(2))]),
        D({ marginTop: 14 }, v.splitTaken.map(function (x, i) {
          return D({ key: i, display: 'flex', gap: 10, alignItems: 'center', padding: '11px 0', borderBottom: '1px solid ' + C.hair }, [
            D({ font: '500 10px/1.4 ' + mono, color: C.ok, width: 52 }, 'TAKEN'),
            D({ font: '450 13.5px/1.4 ' + sans, flex: 1 }, x[0]),
            D({ font: '500 13px/1.2 ' + mono }, x[1].toFixed(2))
          ]);
        })),
        left > 0 ? D({ marginTop: 14, padding: '13px 14px', background: C.sunk, borderRadius: 4 }, [
          D({ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }, [D({ font: '500 13.5px/1.4 ' + sans }, 'Still to collect'), D({ font: '500 19px/1.15 ' + mono, color: C.warn }, 'JOD ' + left.toFixed(2))]),
          D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 7 }, 'The running remainder is always the largest number on screen after the total. A split that ends 50 fils short is the most common cash-drawer discrepancy there is.')
        ]) : D({ marginTop: 14, padding: '13px 14px', border: '1px solid ' + C.ok, borderRadius: 4, font: '400 13px/1.65 ' + sans, color: '#2c2a26' }, 'Fully collected. Everything settles together now — wallet, cash and card in one transaction.'),
        D({ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }, left > 0 ? [
          sec('Wallet · 12.50', function () { v.act('split', ['Wallet', 12.5]); }, true),
          sec('Cash · 20.00', function () { v.act('split', ['Cash', 20]); }, true),
          prim('Card · ' + left.toFixed(2), function () { v.act('split', ['Card', left]); }, true)
        ] : [prim('Complete the sale', function () { v.openScreen('POS-07'); }, true), sec('Start over', function () { v.act('payReset'); }, true)])
      ]))
    ]);
  };

  S['POS-07'] = function (v) {
    return page([
      h1('Receipt', 'POS-07 · bilingual · tax fields · JoFotara reference'),
      card(D({ padding: '20px 22px', maxWidth: 380 }, [
        D({ textAlign: 'center' }, [D({ font: '500 15px/1.3 ' + sans }, 'Nadi Group · Khalda'), D({ font: '400 11px/1.6 ' + ar, color: C.t2, marginTop: 3 }, 'مجموعة نادي · خلدا'), D({ font: '400 10.5px/1.5 ' + mono, color: C.t2, marginTop: 5 }, 'Tax no. 1099238471')]),
        D({ height: 1, background: 'rgba(23,23,26,.14)', margin: '14px 0' }),
        D({}, [['Water 500ml × 2', '1.00'], ['Protein bar', '2.00'], ['Club membership · August', '55.00']].map(function (r, i) {
          return D({ key: i, display: 'flex', justifyContent: 'space-between', padding: '5px 0' }, [D({ font: '400 12px/1.5 ' + sans }, r[0]), D({ font: '500 12px/1.2 ' + mono }, r[1])]);
        })),
        D({ height: 1, background: 'rgba(23,23,26,.1)', margin: '10px 0' }),
        D({ display: 'flex', justifyContent: 'space-between' }, [D({ font: '400 12px/1.5 ' + sans, color: C.t2 }, 'Sales tax 16% · retail only'), D({ font: '500 12px/1.2 ' + mono }, '0.48')]),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(23,23,26,.14)' }, [D({ font: '500 14px/1.3 ' + sans }, 'Total'), D({ font: '500 17px/1.15 ' + mono }, 'JOD 58.48')]),
        D({ font: '400 10.5px/1.6 ' + mono, color: C.t2, marginTop: 12 }, 'Card ···4417 · 19 Aug 18:44\nJoFotara ref JO-2025-8841002\nreceipt no. R-40188'),
        D({ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }, [sec('Print', function () { v.act('flash', 'Printing'); }), sec('WhatsApp', function () { v.act('flash', 'Receipt sent by WhatsApp'); }), prim('Done', function () { v.openScreen('FD-01'); })])
      ]))
    ]);
  };

  // ---- Console ----
  S['CON-01'] = function (v) {
    return page([
      D({ display: 'flex', gap: 11, padding: '12px 16px', background: '#f4ece5', border: '1px solid rgba(138,59,31,.3)', borderRadius: 4, alignItems: 'flex-start' }, [
        D({ width: 3, alignSelf: 'stretch', background: C.err, flexShrink: 0 }),
        D({ flex: 1 }, [
          D({ font: '500 13.5px/1.35 ' + sans }, 'Payment provider degraded · 3 tenants affected'),
          D({ font: '400 12.5px/1.6 ' + sans, color: '#3d3b36', marginTop: 3 }, 'Card authorisations failing intermittently in Jordan since 08:52. Cash, CliQ and check-in unaffected everywhere. 41 failed authorisations, all queued for retry, none charged twice.'),
          D({ display: 'flex', gap: 8, marginTop: 9, flexWrap: 'wrap' }, [prim('Open the incident', function () { v.openScreen('CON-08'); }), sec('Notify the 3 tenants', function () { v.act('flash', 'Notification drafted for 3 tenants'); })])
        ])
      ]),
      h1('184 tenants · 3 need attention', 'MRR JOD 148,200 · 11 in onboarding · 2 churn risks'),
      card(D({ overflowX: 'auto' }, D({ minWidth: 820 }, [
        D({ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) 96px 74px 104px 100px minmax(0,1fr)', gap: 12, padding: '9px 14px', background: C.sunk, borderBottom: '1px solid ' + C.hair, font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, ['TENANT', 'PLAN', 'CLUBS', 'MRR', 'HEALTH', 'NOW'].map(function (x, i) { return D({ key: i }, x); })),
        D({}, [
          ['Nadi Group', 'Growth', '3', '2,400.00', 'GOOD', C.ok, '18 auth failures', C.err],
          ['Fit Republic', 'Enterprise', '14', '9,800.00', 'GOOD', C.ok, '19 auth failures', C.err],
          ['Studio Nine', 'Starter', '1', '280.00', 'AT RISK', C.warn, '4 auth failures', C.err],
          ['Iron House Riyadh', 'Growth', '5', '4,100.00', 'GOOD', C.ok, '—', C.t2],
          ['Pulse Amman', 'Starter', '1', '280.00', 'ONBOARDING', C.info, 'day 4 · import pending', C.t2]
        ].map(function (r, i) {
          return Btn(function () { v.openScreen(r[4] === 'ONBOARDING' ? 'CON-02' : 'CON-17'); }, { key: i, display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) 96px 74px 104px 100px minmax(0,1fr)', gap: 12, padding: '0 14px', height: 34, alignItems: 'center', borderBottom: '1px solid rgba(23,23,26,.06)' }, [
            D({ font: '450 12px/1.3 ' + sans }, r[0]), D({ font: '400 11px/1.3 ' + mono, color: C.t2 }, r[1]),
            D({ font: '400 11px/1.3 ' + mono, color: C.t2 }, r[2]), D({ font: '500 11.5px/1.2 ' + mono }, r[3]),
            D({ font: '500 10px/1.4 ' + mono, color: r[5] }, r[4]), D({ font: '400 11px/1.4 ' + sans, color: r[7] }, r[6])
          ]);
        }))
      ]))),
      card(D({ padding: '12px 14px' }, D({ font: '400 11.5px/1.62 ' + sans, color: '#3d3b36' }, 'No member data on this screen. Counts and health signals only — an engineer can see that Nadi Group had 18 authorisation failures, not who they were. Opening a tenant’s own data requires an impersonation session with a stated reason, a time limit, and a line in the audit log the tenant can read.')))
    ]);
  };

  S['CON-08'] = function (v) {
    return page([
      h1('Payment provider degraded', 'CON-08 · detected 08:54 · 28 minutes · retrying'),
      metrics([['TENANTS AFFECTED', '3', 'of 184'], ['FAILED AUTHS', '41', 'all queued'], ['DOUBLE CHARGES', '0', 'verified'], ['UNAFFECTED', 'cash, CliQ, access', 'everywhere']]),
      card(D({}, [
        D({ padding: '10px 14px', background: C.sunk, borderBottom: '1px solid ' + C.hair }, eyebrow('TIMELINE')),
        D({}, [['08:52', 'First declined authorisation · Nadi Group'], ['08:54', 'Threshold crossed · incident opened automatically'], ['09:02', 'Provider status page confirms degradation'], ['09:08', 'Retry queue enabled for all affected tenants'], ['09:20', 'Tenant notification drafted, awaiting send']].map(function (r, i) {
          return D({ key: i, display: 'flex', gap: 12, padding: '9px 14px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [D({ font: '400 10.5px/1.4 ' + mono, color: C.t2, width: 44, flexShrink: 0 }, r[0]), D({ font: '400 12px/1.45 ' + sans, flex: 1 }, r[1])]);
        }))
      ])),
      D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [prim('Send the notification', function () { v.act('flash', 'Sent to 3 tenant admins · recorded on the incident'); }), sec('Investigate a tenant', function () { v.openScreen('CON-09'); })])
    ]);
  };

  S['CON-09'] = function (v) {
    if (v.impersonating) {
      return page([
        D({ display: 'flex', gap: 10, padding: '12px 15px', background: '#f4ece5', border: '1px solid rgba(138,59,31,.3)', borderRadius: 4, alignItems: 'center', flexWrap: 'wrap' }, [
          D({ width: 3, height: 30, background: C.err, flexShrink: 0 }),
          D({ flex: 1, minWidth: 200 }, [D({ font: '500 12.5px/1.35 ' + sans }, 'Viewing Nadi Group · read only'), D({ font: '400 11px/1.4 ' + mono, color: C.t2, marginTop: 2 }, '21 minutes left · ticket #4182')]),
          Btn(function () { v.act('flash', 'Session ended — logged'); }, { font: '500 11.5px/1 ' + sans, background: C.err, color: C.surf, padding: '9px 12px', borderRadius: 6 }, 'End now')
        ]),
        card(D({ padding: '16px 18px' }, [
          D({ font: '500 15px/1.35 ' + sans }, 'You are inside their tenant now'),
          D({ font: '400 13px/1.68 ' + sans, color: '#3d3b36', marginTop: 6 }, 'Every page view is logged with its screen ID. The bar above cannot be dismissed or scrolled away on any screen. When the timer expires the session ends mid-action — unsaved work is discarded rather than the clock extended.'),
          D({ marginTop: 13 }, prim('Open their Command Center', function () { v.openScreen('ADM-CC-01'); }))
        ])),
        card(D({ padding: '14px 16px' }, [
          eyebrow('HIDDEN EVEN HERE', C.err),
          D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 7 }, 'Biometric templates, stored card numbers and clinical nutrition notes are not rendered and not fetched in any impersonation session at any level. A support engineer debugging a roster does not need a member’s medical history, and the architecture makes it impossible rather than discouraged.')
        ]))
      ]);
    }
    return page([
      D({ border: '1px solid ' + C.err, borderRadius: 6, overflow: 'hidden', maxWidth: 620 }, [
        D({ padding: '10px 16px', background: C.err, font: '500 10px/1.4 ' + mono, color: C.surf, letterSpacing: '.07em' }, 'START AN IMPERSONATION SESSION · TIER 4'),
        D({ padding: '16px 18px', background: C.surf }, [
          D({ font: '500 17px/1.3 ' + sans }, 'Access Nadi Group as an administrator'),
          D({ font: '400 13px/1.68 ' + sans, color: '#3d3b36', marginTop: 6 }, 'You will see their real member data, including names, phone numbers, payment records and health notes. Nadi Group is notified immediately and this session appears in an audit log they can read.'),
          D({ marginTop: 16 }, [eyebrow('WHY · REQUIRED, AND THEY WILL READ IT'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, border: '1px solid rgba(23,23,26,.2)', borderRadius: 6, padding: '11px 12px', marginTop: 6 }, 'Support ticket #4182 — Rania reports the Khalda class roster showing the wrong coach')]),
          D({ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }, [
            D({ flex: 1, minWidth: 150 }, [eyebrow('FOR HOW LONG'), D({ display: 'flex', gap: 7, marginTop: 6 }, [D({ font: '500 11.5px/1 ' + sans, background: C.t1, color: C.surf, padding: '9px 11px', borderRadius: 6 }, '30 min'), D({ font: '400 11.5px/1 ' + sans, border: '1px solid rgba(23,23,26,.2)', padding: '8px 10px', borderRadius: 6 }, '2 hours')])]),
            D({ flex: 1, minWidth: 150 }, [eyebrow('ACCESS LEVEL'), D({ display: 'flex', gap: 7, marginTop: 6 }, [D({ font: '500 11.5px/1 ' + sans, background: C.t1, color: C.surf, padding: '9px 11px', borderRadius: 6 }, 'Read only'), D({ font: '400 11.5px/1 ' + sans, border: '1px solid rgba(23,23,26,.2)', padding: '8px 10px', borderRadius: 6 }, 'Can act')])])
          ]),
          D({ marginTop: 14, padding: '12px 13px', background: C.sunk, borderRadius: 4, font: '400 12px/1.65 ' + sans, color: '#3d3b36' }, 'Read-only is the default and covers most support work. “Can act” requires a second Veyro approver and is limited to 30 minutes regardless of what is selected above.'),
          D({ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }, [
            Btn(function () { v.act('impersonate'); }, { font: '500 13px/1 ' + sans, background: C.err, color: C.surf, padding: '13px 15px', borderRadius: 6 }, 'Start read-only session'),
            sec('Cancel', function () { v.openScreen('CON-01'); })
          ])
        ])
      ])
    ]);
  };

  // ---------- MOBILE ----------




  function memberHeader(v, name, meta, badgeTxt, badgeCol) {
    return D({ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }, [
      D({ width: 46, height: 46, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
      D({ flex: 1, minWidth: 220 }, [
        D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [
          D({ font: '500 21px/1.2 ' + sans, letterSpacing: '-.015em' }, name),
          badgeTxt ? badge(badgeTxt, badgeCol) : null
        ]),
        D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 4 }, meta)
      ]),
      D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [sec('Message', function () { v.openScreen('ADM-COM-01'); }), sec('⋯', function () {})])
    ]);
  }
  function noteRow(who, when, text) {
    return D({ padding: '13px 15px', borderTop: '1px solid ' + C.hair }, [
      D({ display: 'flex', gap: 9, alignItems: 'baseline' }, [
        D({ font: '500 12px/1.4 ' + sans }, who),
        D({ font: '400 10.5px/1.4 ' + mono, color: C.t2 }, when)
      ]),
      D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 4 }, text)
    ]);
  }
  function mergeRow(label, a, b) {
    return D({ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 12, padding: '11px 16px', borderTop: '1px solid ' + C.hair, alignItems: 'center' }, [
      D({ font: '400 11.5px/1.4 ' + mono, color: C.t2 }, label),
      D({ font: '450 12.5px/1.4 ' + sans }, a),
      D({ font: '400 12.5px/1.4 ' + sans, color: C.t2 }, b)
    ]);
  }


  function ruleRow(label, text) {
    return D({ padding: '14px 16px', borderTop: '1px solid ' + C.hair, maxWidth: 620 }, [
      D({ font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.07em' }, label),
      D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 5 }, text)
    ]);
  }



  function barRow(label, val, delta, pct, col) {
    return D({ marginTop: 9 }, [
      D({ display: 'flex', gap: 8, alignItems: 'baseline' }, [
        D({ font: '450 12.5px/1.4 ' + sans, flex: 1 }, label),
        D({ font: '500 12.5px/1.2 ' + mono }, val),
        D({ font: '500 11px/1.2 ' + mono, color: col, width: 52, textAlign: 'end' }, delta)
      ]),
      D({ height: 3, background: '#ece9e3', marginTop: 5, borderRadius: 2, overflow: 'hidden' }, D({ height: 3, width: pct + '%', background: col === C.err ? C.err : '#57544d' }))
    ]);
  }
  function intRow(name, state, detail, col) {
    return D({ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 16px', borderTop: '1px solid ' + C.hair, flexWrap: 'wrap' }, [
      D({ flex: 1, minWidth: 180 }, [D({ font: '450 13.5px/1.4 ' + sans }, name), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, state)]),
      D({ font: '400 11.5px/1.4 ' + mono, color: col }, detail)
    ]);
  }

  function permRow(name, on, note) {
    return D({ display: 'flex', gap: 12, alignItems: 'center', padding: '13px 15px', borderTop: '1px solid ' + C.hair, flexWrap: 'wrap' }, [
      D({ flex: 1, minWidth: 180 }, [D({ font: '450 13px/1.4 ' + sans }, name), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, note)]),
      D({ font: '500 11px/1.4 ' + mono, color: on ? C.ok : C.ctl }, on ? 'GRANTED' : 'NOT GRANTED')
    ]);
  }

  function credRow(name, detail, col, action) {
    return D({ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 16px', borderTop: '1px solid ' + C.hair, flexWrap: 'wrap' }, [
      D({ flex: 1, minWidth: 180 }, [D({ font: '450 13.5px/1.4 ' + sans }, name), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, detail)]),
      D({ font: '500 11px/1.4 ' + mono, color: col, width: 60 }, 'ACTIVE'),
      sec(action, function () {})
    ]);
  }

  function evRow(text, has) {
    return D({ display: 'flex', gap: 11, alignItems: 'center', padding: '12px 15px', borderTop: '1px solid ' + C.hair }, [
      D({ font: '400 12px/1 ' + mono, color: has ? C.ok : C.ctl, width: 14 }, has ? '☑' : '☐'),
      D({ font: '400 12.5px/1.55 ' + sans, flex: 1, color: has ? C.t1 : C.t2 }, text)
    ]);
  }

  function stat(val, label) { return D({}, [D({ font: '500 19px/1.15 ' + mono }, val), D({ font: '400 9.5px/1.4 ' + mono, color: C.t2, marginTop: 4 }, label)]); }
  function staleMetric(label, val, sub, stale) {
    return D({ background: C.surf, padding: '12px 14px' }, [
      D({ font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.07em' }, label),
      D({ font: '500 19px/1.15 ' + mono, marginTop: 6, color: stale ? C.t2 : C.t1 }, val),
      D({ font: '400 10px/1.4 ' + mono, color: stale ? C.warn : C.ok, marginTop: 4 }, sub)
    ]);
  }
  function attnRow(v, tag, col, title, body, cta, dest) {
    return D({ display: 'flex' }, [
      D({ width: 3, background: col, flexShrink: 0 }),
      D({ flex: 1, padding: '13px 15px', minWidth: 0 }, [
        D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [badge(tag, col)]),
        D({ font: '500 15px/1.35 ' + sans, marginTop: 7 }, title),
        D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 4, maxWidth: '88ch' }, body),
        D({ display: 'flex', gap: 8, marginTop: 11, flexWrap: 'wrap' }, [prim(cta, function () { v.openScreen(dest); }), sec('Review', function () { v.openScreen(dest); })])
      ])
    ]);
  }
  function condRow(v, tag, col, text, dest) {
    return D({ display: 'flex', borderTop: '1px solid ' + C.hair, background: C.sunk }, [
      D({ width: 3, background: col, flexShrink: 0 }),
      D({ flex: 1, padding: '11px 15px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }, [
        badge(tag, col),
        D({ font: '450 12.5px/1.5 ' + sans, flex: 1, minWidth: 200 }, text),
        Btn(function () { v.openScreen(dest); }, { font: '400 11.5px/1 ' + sans, color: C.ink, minHeight: 44, display: 'flex', alignItems: 'center' }, 'View')
      ])
    ]);
  }
  function filterBar(chips) {
    return D({ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap', alignItems: 'center' }, chips.map(function (c, i) {
      return i === 0
        ? Btn(function () {}, { font: '500 11.5px/1 ' + sans, background: C.t1, color: C.surf, padding: '9px 11px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, c)
        : sec(c, function () {});
    }));
  }
  function table(heads, rows, onRow) {
    var cols = heads.map(function () { return 'minmax(0,1fr)'; }).join(' ');
    return D({ border: '1px solid ' + C.line, borderRadius: 4, background: C.surf, overflowX: 'auto', marginTop: 14 }, [
      D({ minWidth: 620, display: 'grid', gridTemplateColumns: cols, gap: 12, padding: '9px 16px', background: C.sunk, borderBottom: '1px solid ' + C.line }, heads.map(function (x, i) {
        return D({ key: i, font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, x);
      }))
    ].concat(rows.map(function (r, i) {
      return Btn(onRow, { minWidth: 620, display: 'grid', gridTemplateColumns: cols, gap: 12, padding: '0 16px', height: 40, alignItems: 'center', borderBottom: i < rows.length - 1 ? '1px solid ' + C.hair : 'none' }, r.map(function (c, j) {
        if (c && typeof c === 'object') return D({ key: j, font: '500 10px/1.4 ' + mono, color: c.c || C.t2 }, c.t);
        return D({ key: j, font: j === 0 ? '450 12px/1.3 ' + sans : '400 11px/1.3 ' + mono, color: j === 0 ? C.t1 : C.t2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, c);
      }));
    })));
  }
  function tl(when, what, detail) {
    return D({ display: 'flex', gap: 12, padding: '11px 15px', borderTop: '1px solid ' + C.hair }, [
      D({ font: '400 10.5px/1.5 ' + mono, color: C.t2, width: 84, flexShrink: 0 }, when),
      D({ flex: 1 }, [D({ font: '450 12.5px/1.45 ' + sans }, what), detail ? D({ font: '400 11.5px/1.55 ' + sans, color: C.t2, marginTop: 2 }, detail) : null])
    ]);
  }
  function aiPanel(rec, why, v) {
    return D({ border: '1px solid #4a3d7a', borderRadius: 4, marginTop: 16, overflow: 'hidden', maxWidth: 620 }, [
      D({ padding: '9px 14px', background: '#edebf6', display: 'flex', gap: 8, alignItems: 'center' }, [
        D({ font: '400 10.5px/1 ' + mono, color: '#4a3d7a' }, '✦'),
        D({ font: '500 10px/1.4 ' + mono, color: '#4a3d7a', letterSpacing: '.07em' }, 'VEYRO SUGGESTS · YOU DECIDE')
      ]),
      D({ padding: '14px 15px' }, [
        D({ font: '450 14px/1.55 ' + sans, color: C.t1 }, rec),
        D({ font: '400 12.5px/1.65 ' + sans, color: '#3d3b36', marginTop: 7 }, why),
        D({ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }, [
          prim('Preview the message', function () { v.act('flash', 'Draft ready for your approval'); }),
          sec('Just the trial', function () {})
        ])
      ])
    ]);
  }

  function dPage(kids) { DARK = false; return D({ padding: '20px 22px 26px', background: C.canvas, minHeight: '100%' }, kids); }
  function metric(label, val, sub) {
    return D({ background: C.surf, padding: '12px 14px' }, [
      D({ font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.07em' }, label),
      D({ font: '500 19px/1.15 ' + mono, marginTop: 6 }, val),
      sub ? D({ font: '400 10.5px/1.4 ' + sans, color: C.t2, marginTop: 4 }, sub) : null
    ]);
  }

  function tPage(kids) { DARK = false; return D({ padding: '20px 22px 26px', background: C.canvas, minHeight: '100%' }, kids); }
  function field(label, val) {
    return D({}, [
      D({ font: '500 10px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, label.toUpperCase()),
      D({ font: '400 15px/1.4 ' + sans, border: '1px solid ' + C.line, borderRadius: 6, padding: '13px 14px', marginTop: 5, minHeight: 48, display: 'flex', alignItems: 'center' }, val)
    ]);
  }
  function row(l, r) {
    return D({ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 5 }, [
      D({ font: '400 13px/1.6 ' + sans, color: '#3d3b36' }, l),
      D({ font: '500 13px/1.2 ' + mono }, r)
    ]);
  }
  function planRow(name, desc, price, on) {
    return D({ display: 'flex', gap: 12, alignItems: 'center', padding: '15px 16px', border: on ? '2px solid ' + C.ink : 'none', borderTop: on ? '2px solid ' + C.ink : '1px solid ' + C.hair, background: on ? '#f7f9fc' : 'transparent', minHeight: 48 }, [
      D({ flex: 1 }, [D({ font: '450 15px/1.35 ' + sans }, name), D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 2 }, desc)]),
      D({ font: '500 15px/1.2 ' + mono }, price)
    ]);
  }

  function mPage(kids, dark) {
    DARK = !!dark;
    return D({ padding: '10px 18px 20px', background: dark ? C.dBg : C.surf, minHeight: '100%', display: 'flex', flexDirection: 'column', gap: 0 }, kids);
  }

  S['CCH-01'] = function (v) {
    return mPage([
      D({ display: 'flex', gap: 10, alignItems: 'baseline' }, [
        D({ flex: 1 }, [D({ font: '500 26px/1.15 ' + sans, letterSpacing: '-.018em' }, 'Wednesday'), D({ font: '400 13px/1.5 ' + sans, color: C.t2, marginTop: 2 }, '4 sessions · 2 need you first')]),
        D({ width: 34, height: 34, borderRadius: '50%', background: '#dcd7cf' })
      ]),
      D({ border: '1px solid ' + C.warn, borderRadius: 6, marginTop: 16, overflow: 'hidden' }, D({ display: 'flex' }, [
        D({ width: 3, background: C.warn, flexShrink: 0 }),
        D({ flex: 1, padding: '13px 14px' }, [
          D({ font: '500 15px/1.35 ' + sans }, '31 sessions need your sign-off'),
          D({ font: '400 12.5px/1.6 ' + sans, color: '#3d3b36', marginTop: 3 }, "22 yours, back to 1 August. Members can't see their remaining credits until you confirm these happened."),
          D({ marginTop: 11 }, prim('Confirm all 22', function () { v.act('flash', 'All 22 verified — credits updated, members notified'); }, true))
        ])
      ])),
      D({ marginTop: 20 }, eyebrow('NOW')),
      D({ border: '2px solid ' + C.ink, borderRadius: 6, padding: '14px 15px', marginTop: 8 }, [
        D({ display: 'flex', gap: 11, alignItems: 'center' }, [
          D({ width: 44, height: 44, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
          D({ flex: 1 }, [D({ font: '500 17px/1.25 ' + sans }, 'Ahmad Nabulsi'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, '09:45 · lower body · week 8 of 12')])
        ]),
        D({ font: '400 13px/1.62 ' + sans, color: '#2c2a26', marginTop: 10, background: C.sunk, padding: '10px 12px', borderRadius: 4 }, "Hasn't trained in 19 days. Last session he squatted 82.5kg for 5 — don't open there."),
        D({ marginTop: 12 }, Btn(function () { v.openScreen('CCH-02'); }, { font: '500 15px/1 ' + sans, background: C.ink, color: C.surf, padding: '17px 16px', borderRadius: 6, textAlign: 'center' }, 'Start session')),
        D({ marginTop: 8 }, Btn(function () { v.openScreen('CCH-05'); }, { font: '450 13px/1 ' + sans, color: C.ink, textAlign: 'center', padding: '10px' }, 'See his profile first'))
      ]),
      D({ marginTop: 20 }, eyebrow('LATER TODAY')),
      D({ marginTop: 8 }, [['11:00', 'Dana Qasem', 'upper body · on track', C.t2], ['17:30', 'Hala Barakat', 'asked about her plan', C.warn], ['19:00', 'Spin · 18 booked', 'covering for Omar', C.t2]].map(function (r, i) {
        return Btn(function () { v.openScreen('CCH-05'); }, { key: i, display: 'flex', gap: 11, alignItems: 'center', padding: '12px 4px', borderBottom: i < 2 ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '500 12px/1.3 ' + mono, width: 44, flexShrink: 0 }, r[0]),
          D({ width: 32, height: 32, borderRadius: '50%', background: '#ece9e3', flexShrink: 0 }),
          D({ flex: 1, minWidth: 0 }, [D({ font: '450 14.5px/1.3 ' + sans }, r[1]), D({ font: '400 11.5px/1.4 ' + mono, color: r[3], marginTop: 2 }, r[2])])
        ]);
      }))
    ]);
  };

  S['CCH-02'] = function (v) {
    var logged = function (k) { return !!v.sets[k]; };
    var s3 = logged('c3');
    return mPage([
      D({ display: 'flex', gap: 10, alignItems: 'center' }, [
        D({ flex: 1 }, [D({ font: '500 19px/1.2 ' + sans, color: C.dT1 }, 'Ahmad · lower body'), D({ font: '400 12px/1.5 ' + mono, color: C.dT3, marginTop: 3 }, '27 min · exercise 3 of 5')]),
        Btn(function () { v.openScreen('CCH-07'); }, { font: '450 12px/1 ' + sans, color: C.dT1, border: '1px solid rgba(255,255,255,.24)', padding: '11px 12px', minHeight: 44, display: 'inline-flex', alignItems: 'center', borderRadius: 6 }, 'End')
      ]),
      D({ border: '1px solid ' + C.dLine, borderRadius: 6, background: C.dSurf, marginTop: 16, overflow: 'hidden' }, [
        D({ padding: '12px 14px', borderBottom: '1px solid rgba(255,255,255,.1)' }, D({ display: 'flex', gap: 9, alignItems: 'baseline' }, [D({ font: '500 16px/1.3 ' + sans, color: C.dT1, flex: 1 }, 'Back squat'), D({ font: '400 11.5px/1.4 ' + mono, color: C.dT3 }, 'last: 82.5 × 5')])),
        D({ padding: '4px 0' }, [
          D({ display: 'flex', gap: 12, alignItems: 'center', padding: '11px 14px', borderBottom: '1px solid rgba(255,255,255,.06)' }, [D({ font: '400 11px/1.4 ' + mono, color: C.dT3, width: 16 }, '1'), D({ font: '500 16px/1.2 ' + mono, color: C.dT1 }, '60.0 kg × 8'), D({ flex: 1 }), D({ font: '500 11px/1.4 ' + mono, color: C.dOk }, 'DONE')]),
          D({ display: 'flex', gap: 12, alignItems: 'center', padding: '11px 14px', borderBottom: '1px solid rgba(255,255,255,.06)' }, [D({ font: '400 11px/1.4 ' + mono, color: C.dT3, width: 16 }, '2'), D({ font: '500 16px/1.2 ' + mono, color: C.dT1 }, '70.0 kg × 6'), D({ flex: 1 }), D({ font: '500 11px/1.4 ' + mono, color: C.dOk }, 'DONE')]),
          D({ display: 'flex', gap: 12, alignItems: 'center', padding: '13px 14px', background: s3 ? 'transparent' : 'rgba(126,166,232,.12)', borderInlineStart: s3 ? '2px solid transparent' : '2px solid ' + C.dAcc }, [
            D({ font: '400 11px/1.4 ' + mono, color: s3 ? C.dT3 : C.dAcc, width: 16 }, '3'),
            D({ font: '500 ' + (s3 ? 16 : 20) + 'px/1.2 ' + mono, color: C.dT1 }, '75.0 kg × 5'),
            D({ flex: 1 }),
            s3 ? D({ font: '500 11px/1.4 ' + mono, color: C.dOk }, 'DONE')
              : Btn(function () { v.act('logSet', 'c3'); }, { font: '500 12px/1 ' + sans, background: C.dAcc, color: '#12233d', padding: '12px 14px', minHeight: 44, display: 'inline-flex', alignItems: 'center', borderRadius: 6 }, 'Log')
          ]),
          s3 ? D({ display: 'flex', gap: 12, alignItems: 'center', padding: '13px 14px', background: 'rgba(126,166,232,.12)', borderInlineStart: '2px solid ' + C.dAcc }, [
            D({ font: '400 11px/1.4 ' + mono, color: C.dAcc, width: 16 }, '4'),
            D({ font: '500 20px/1.2 ' + mono, color: C.dT1 }, '75.0 kg × 5'),
            D({ flex: 1 }),
            Btn(function () { v.act('logSet', 'c4'); }, { font: '500 12px/1 ' + sans, background: C.dAcc, color: '#12233d', padding: '12px 14px', minHeight: 44, display: 'inline-flex', alignItems: 'center', borderRadius: 6 }, 'Log')
          ]) : null
        ]),
        D({ padding: '11px 14px', borderTop: '1px solid rgba(255,255,255,.1)', font: '400 12.5px/1.5 ' + sans, color: C.dT2 }, s3 ? 'Rest 2:00 · running' : 'Rest 2:00 starts when you log')
      ]),
      D({ border: '1px solid rgba(255,255,255,.12)', borderRadius: 6, background: C.dSurf, padding: '12px 14px', marginTop: 14 }, [
        D({ font: '400 12.5px/1.7 ' + sans, color: C.dT2 }, 'He stopped at 5 on set 2 and said his knee felt tight. Dropped him to 75 rather than pushing to 82.5.'),
        D({ font: '400 10.5px/1.5 ' + mono, color: C.dT3, marginTop: 7 }, 'Voice note · 14s · transcribed · saved to his record')
      ]),
      D({ marginTop: 14 }, Btn(function () { v.openScreen('CCH-07'); }, { font: '500 14px/1 ' + sans, background: C.dAcc, color: '#12233d', padding: '16px', borderRadius: 6, textAlign: 'center' }, 'Finish and verify')),
      D({ font: '400 11px/1.5 ' + mono, color: C.dT3, marginTop: 11, textAlign: 'center' }, 'Everything logs offline · syncs when you leave the basement')
    ], true);
  };

  S['CCH-07'] = function (v) {
    return mPage([
      D({ font: '500 26px/1.15 ' + sans, letterSpacing: '-.018em' }, 'Session done'),
      D({ font: '400 14px/1.62 ' + sans, color: '#3d3b36', marginTop: 8 }, 'Ahmad · lower body · 41 minutes · 5 exercises · 18 sets'),
      card(D({ padding: '14px 15px' }, [
        eyebrow('ONE TAP DOES ALL OF THIS'),
        D({ font: '400 13px/1.85 ' + sans, color: '#2c2a26', marginTop: 7 }, 'Verifies the session · decrements his credit to 3 of 10 · updates his app · attaches your note · offers his next booking'),
        D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 9 }, 'No separate verification screen. That second visit to a different place is exactly why 31 sessions went unverified in the old flow.')
      ]), { marginTop: 16 }),
      D({ marginTop: 16 }, Btn(function () { v.act('flash', 'Verified — credit 3 of 10 remaining, Ahmad notified'); }, { font: '500 15px/1 ' + sans, background: C.ink, color: C.surf, padding: '17px', borderRadius: 6, textAlign: 'center' }, 'Verify and close')),
      D({ marginTop: 9 }, Btn(function () { v.openScreen('CCH-01'); }, { font: '450 13px/1 ' + sans, color: C.t2, textAlign: 'center', padding: '12px' }, 'Back to today'))
    ]);
  };

  S['CCH-05'] = function (v) {
    var wk = ['#2f5d3a', '#2f5d3a', '#2f5d3a', '#2f5d3a', '#2f5d3a', '#8a5a1f', '#2f5d3a', '#2f5d3a', '#ece9e3', '#ece9e3', '#ece9e3', '#ece9e3'];
    return mPage([
      D({ display: 'flex', gap: 12, alignItems: 'center' }, [
        D({ width: 48, height: 48, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
        D({ flex: 1 }, [D({ font: '500 19px/1.25 ' + sans }, 'Ahmad Nabulsi'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, 'Week 8 of 12 · 4 credits left')])
      ]),
      D({ border: '1px solid ' + C.warn, borderRadius: 6, marginTop: 14, overflow: 'hidden' }, D({ display: 'flex' }, [
        D({ width: 3, background: C.warn, flexShrink: 0 }),
        D({ flex: 1, padding: '12px 13px' }, [D({ font: '500 14px/1.35 ' + sans }, '19 days since he trained'), D({ font: '400 12.5px/1.6 ' + sans, color: '#3d3b36', marginTop: 3 }, 'Was coming 3× a week. No message, no cancellation — he just stopped. Session today at 09:45.')])
      ])),
      D({ marginTop: 16 }, eyebrow('CURRENT PROGRAMME')),
      card(D({ padding: '12px 13px' }, [
        D({ font: '450 14.5px/1.4 ' + sans }, 'Lower-body strength · 12 weeks'),
        D({ display: 'flex', gap: 3, marginTop: 9 }, wk.map(function (c, i) { return D({ key: i, flex: 1, height: 6, borderRadius: 1, background: c }); })),
        D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 7 }, '8 done · 1 missed · 3 remaining')
      ]), { marginTop: 8 }),
      D({ marginTop: 16 }, eyebrow('LAST SESSION · 31 JULY')),
      card(D({ padding: '12px 13px' }, [
        D({ font: '400 12.5px/1.7 ' + sans, color: '#3d3b36' }, 'Squat 82.5 × 5 · RDL 100 × 8 · leg press 180 × 10'),
        D({ font: '400 12px/1.65 ' + sans, color: C.t2, marginTop: 7, paddingTop: 7, borderTop: '1px solid rgba(23,23,26,.08)' }, '"Knee felt tight on the second set. Watch it next time."')
      ]), { marginTop: 8 }),
      D({ marginTop: 14, padding: '11px 12px', background: C.sunk, borderRadius: 4 }, [
        D({ font: '500 11.5px/1.4 ' + sans }, 'Limitations'),
        D({ font: '400 12px/1.65 ' + sans, color: '#3d3b36', marginTop: 4 }, 'Left knee — previous meniscus surgery, 2019. No deep loaded flexion. Recorded at intake.')
      ]),
      D({ marginTop: 16 }, Btn(function () { v.openScreen('CCH-02'); }, { font: '500 15px/1 ' + sans, background: C.ink, color: C.surf, padding: '16px', borderRadius: 6, textAlign: 'center' }, "Start today's session")),
      D({ marginTop: 9 }, Btn(function () { v.openScreen('CCH-03'); }, { font: '450 13px/1 ' + sans, color: C.ink, textAlign: 'center', padding: '11px' }, 'His nutrition plan'))
    ]);
  };

  S['CCH-03'] = function (v) {
    var assigned = v.nutritionStep === 'assigned';
    return mPage([
      D({ font: '500 20px/1.2 ' + sans, letterSpacing: '-.014em' }, "Ahmad's plan"),
      D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 3 }, assigned ? 'Assigned · he has it now, with a grocery list' : 'Generated in 4 seconds · not assigned yet'),
      D({ border: '1px solid ' + C.ai, borderRadius: 6, marginTop: 14, overflow: 'hidden' }, [
        D({ padding: '9px 13px', background: C.aiWash, display: 'flex', gap: 7, alignItems: 'center' }, [D({ font: '400 10.5px/1 ' + mono, color: C.ai }, '✦'), D({ font: '500 10px/1.4 ' + mono, color: C.ai, letterSpacing: '.06em' }, 'VEYRO DREW THIS FROM HIS RECORD')]),
        D({ padding: '12px 13px' }, [
          D({ font: '400 12.5px/1.7 ' + sans, color: '#2c2a26' }, '78kg, cutting, trains 4 days, no fish, lactose-sensitive. 2,150 kcal · 165P / 210C / 62F.'),
          D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 7 }, 'Based on his last weigh-in 6 days ago and his logged training.')
        ])
      ]),
      D({ display: 'flex', gap: 7, marginTop: 14, flexWrap: 'wrap' }, ['Day 1', '2', '3', '4', '5', '6', '7'].map(function (d, i) {
        return D({ key: i, font: (i ? '400' : '500') + ' 11.5px/1 ' + sans, background: i ? 'transparent' : C.t1, color: i ? C.t1 : C.surf, border: i ? '1px solid rgba(23,23,26,.2)' : 'none', padding: i ? '10px 11px' : '11px 12px', borderRadius: 6 }, d);
      })),
      card(D({}, [
        ['BREAKFAST · 07:30', 'Oats, banana, whey, almond butter', '520 kcal', '38P · 62C · 14F', ''],
        ['LUNCH · 13:00', 'Chicken mansaf-style with rice and yoghurt', '680 kcal', '52P · 74C · 18F', 'Lactose-free yoghurt substituted automatically'],
        ['POST-TRAINING · 18:15', 'Whey and dates', '310 kcal', '30P · 42C · 2F', ''],
        ['DINNER · 20:30', 'Beef kofta, salad, flatbread', '640 kcal', '45P · 32C · 28F', '']
      ].map(function (m, i) {
        return D({ key: i, padding: '12px 13px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ display: 'flex', gap: 8, alignItems: 'baseline' }, [D({ font: '400 10px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em', flex: 1 }, m[0]), D({ font: '500 11.5px/1.2 ' + mono, color: C.t2 }, m[2])]),
          D({ font: '450 14px/1.4 ' + sans, marginTop: 5 }, m[1]),
          D({ font: '400 11.5px/1.5 ' + mono, color: C.t2, marginTop: 3 }, m[3]),
          m[4] ? D({ font: '400 11px/1.5 ' + sans, color: C.warn, marginTop: 5 }, m[4]) : null
        ]);
      })), { marginTop: 12 }),
      D({ marginTop: 14 }, assigned
        ? sec('Back to his profile', function () { v.openScreen('CCH-05'); }, true)
        : Btn(function () { v.act('nutrition', 'assigned'); }, { font: '500 14px/1 ' + sans, background: C.ink, color: C.surf, padding: '16px', borderRadius: 6, textAlign: 'center' }, 'Assign to Ahmad')),
      D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 12 }, 'Ahmad has no flagged condition, so this assigns directly. With one flagged, the Assign button is replaced by “needs review by a qualified professional” and the plan is routed — Veyro defines no clinical criteria.')
    ]);
  };

  S['MBR-01'] = function (v) {
    var ate = !!v.meals.lunch;
    return mPage([
      D({ font: '400 13px/1.5 ' + sans, color: C.t2 }, 'Wednesday morning'),
      D({ font: '500 30px/1.12 ' + sans, letterSpacing: '-.02em', marginTop: 2 }, 'Lower body\nat 09:45'),
      D({ font: '400 14.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 12 }, "With Yousef. It's been a while — he's planning to start lighter than last time."),
      D({ marginTop: 18 }, Btn(function () { v.openScreen('MBR-07'); }, { font: '500 16px/1 ' + sans, background: C.ink, color: C.surf, padding: '19px', borderRadius: 6, textAlign: 'center' }, 'See the session')),
      D({ border: '1px solid ' + C.warn, borderRadius: 6, marginTop: 24, overflow: 'hidden' }, D({ display: 'flex' }, [
        D({ width: 3, background: C.warn, flexShrink: 0 }),
        D({ flex: 1, padding: '15px 16px' }, [
          D({ font: '500 16px/1.35 ' + sans }, 'Your card expired'),
          D({ font: '400 14px/1.62 ' + sans, color: '#3d3b36', marginTop: 4 }, "August's JOD 55.00 didn't go through. You can still train — sort it whenever."),
          D({ marginTop: 13 }, prim('Pay JOD 55.00', function () { v.openScreen('MBR-26'); }, true)),
          D({ marginTop: 12 }, Btn(function () { v.openScreen('MBR-26'); }, { font: '400 13px/1.5 ' + sans, color: C.ink, minHeight: 44, display: 'flex', alignItems: 'center' }, 'Update my card instead'))
        ])
      ])),
      D({ marginTop: 26 }, eyebrow("TODAY'S FOOD")),
      D({ display: 'flex', gap: 14, alignItems: 'baseline', marginTop: 9 }, [
        D({}, [D({ font: '500 24px/1.15 ' + mono }, ate ? '1,200' : '520'), D({ font: '400 10.5px/1.4 ' + mono, color: C.t2, marginTop: 3 }, 'OF 2,150 KCAL')]),
        D({ flex: 1, height: 4, background: '#ece9e3', borderRadius: 2, overflow: 'hidden', marginBottom: 6 }, D({ height: 4, width: (ate ? 56 : 24) + '%', background: C.t2 }))
      ]),
      card(D({}, [
        D({ padding: '14px 15px', borderBottom: '1px solid ' + C.hair, display: 'flex', gap: 11, alignItems: 'center', background: C.sunk }, [
          D({ flex: 1 }, [eyebrow('BREAKFAST'), D({ font: '450 15px/1.4 ' + sans, marginTop: 3 }, 'Oats, banana, whey')]),
          D({ font: '500 11px/1.4 ' + mono, color: C.ok }, 'EATEN')
        ]),
        D({ padding: '14px 15px', borderBottom: '1px solid ' + C.hair, background: ate ? C.sunk : C.surf }, [
          D({ display: 'flex', gap: 11, alignItems: 'center' }, [
            D({ flex: 1 }, [eyebrow('LUNCH · 13:00'), D({ font: '450 15px/1.4 ' + sans, marginTop: 3 }, 'Chicken with rice and yoghurt'), D({ font: '400 12px/1.5 ' + mono, color: C.t2, marginTop: 3 }, '680 kcal · 52P 74C 18F')]),
            ate ? D({ font: '500 11px/1.4 ' + mono, color: C.ok }, 'EATEN') : null
          ]),
          ate ? null : D({ display: 'flex', gap: 9, marginTop: 12 }, [
            D({ flex: 1 }, Btn(function () { v.act('logMeal', 'lunch'); }, { font: '500 14px/1 ' + sans, background: C.ink, color: C.surf, padding: '16px', borderRadius: 6, textAlign: 'center' }, 'Ate it')),
            sec('Swap', function () { v.openScreen('MBR-02'); }, true)
          ])
        ]),
        D({ padding: '14px 15px', opacity: .62 }, [eyebrow('AFTER TRAINING · 18:15'), D({ font: '450 15px/1.4 ' + sans, marginTop: 3 }, 'Whey and dates')])
      ]), { marginTop: 12 }),
      D({ marginTop: 14 }, Btn(function () { v.openScreen('MBR-10'); }, { font: '400 13px/1.5 ' + sans, color: C.ink, minHeight: 44, display: 'flex', alignItems: 'center' }, 'Ate something else →'))
    ]);
  };

  S['MBR-02'] = function (v) {
    var opts = [['Beef shawarma plate', '665 kcal · 50P 68C 21F', ''], ['Grilled chicken shish tawook', '690 kcal · 55P 70C 17F', ''], ['Lentil soup and two flatbreads', '640 kcal · 34P 92C 12F', '18g less protein']];
    return mPage([
      D({ width: 36, height: 4, background: '#cbc6bc', borderRadius: 2, margin: '0 auto 16px' }),
      D({ font: '500 20px/1.2 ' + sans, letterSpacing: '-.014em' }, 'Instead of chicken and rice'),
      D({ font: '400 13.5px/1.6 ' + sans, color: C.t2, marginTop: 5 }, 'Same calories and protein, no fish, lactose-free.'),
      D({ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 16 }, opts.map(function (o, i) {
        return D({ key: i, border: '1px solid rgba(23,23,26,.18)', borderRadius: 6, padding: '14px 15px', display: 'flex', gap: 11, alignItems: 'center' }, [
          D({ flex: 1 }, [
            D({ font: '450 15px/1.4 ' + sans }, o[0]),
            D({ font: '400 12px/1.5 ' + mono, color: C.t2, marginTop: 3 }, o[1] + (o[2] ? '' : '')),
            o[2] ? D({ font: '400 12px/1.5 ' + sans, color: C.warn, marginTop: 3 }, o[2]) : null
          ]),
          Btn(function () { v.act('logMeal', 'lunch'); v.openScreen('MBR-01'); }, { font: '500 13px/1 ' + sans, background: C.ink, color: C.surf, padding: '14px 15px', borderRadius: 6 }, 'Ate it')
        ]);
      })),
      D({ display: 'flex', gap: 9, marginTop: 16 }, [
        D({ flex: 1 }, sec('Search food', function () { v.openScreen('MBR-10'); }, true)),
        D({ flex: 1 }, sec('Photo', function () { v.act('flash', 'Camera — AI estimates the portion, you can edit it'); }, true)),
        D({ flex: 1 }, sec('Barcode', function () { v.act('flash', 'Scanning'); }, true))
      ]),
      D({ font: '400 12px/1.55 ' + sans, color: C.t2, marginTop: 13 }, 'Yousef sees what you actually ate, not what was planned. No need to explain.')
    ]);
  };

  S['MBR-03'] = function (v) {
    var b = v.booked;
    var classes = [['Spin', 'Thursday 19:00', 'Dana', 'full', 3], ['Yoga', 'Thursday 07:00', 'Yousef', '6 places', 0], ['HIIT', 'Friday 18:00', 'Dana', '2 places', 0]];
    return mPage([
      D({ font: '500 26px/1.15 ' + sans, letterSpacing: '-.018em' }, 'Classes'),
      D({ font: '400 13px/1.5 ' + sans, color: C.t2, marginTop: 4 }, 'Khalda · this week'),
      D({ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 18 }, classes.map(function (c, i) {
        var st = b[c[0]];
        return D({ key: i, border: '1px solid ' + (st ? C.ok : 'rgba(23,23,26,.18)'), borderRadius: 6, padding: '15px 16px' }, [
          D({ display: 'flex', gap: 11, alignItems: 'flex-start' }, [
            D({ flex: 1 }, [
              D({ font: '500 17px/1.3 ' + sans }, c[0]),
              D({ font: '400 13px/1.55 ' + sans, color: C.t2, marginTop: 3 }, c[1] + ' · with ' + c[2]),
              D({ font: '400 12px/1.5 ' + mono, color: c[3] === 'full' ? C.warn : C.t2, marginTop: 4 }, c[3] === 'full' ? 'Full · ' + c[4] + ' on the waitlist' : c[3])
            ]),
            st ? badge(st === 'waitlist' ? 'WAITLISTED' : 'BOOKED', st === 'waitlist' ? C.warn : C.ok) : null
          ]),
          st ? D({ font: '400 12.5px/1.6 ' + sans, color: '#3d3b36', marginTop: 10 }, st === 'waitlist' ? 'Position 4. About 1 in 3 waitlisted members get in for Thursday spin. We will book you automatically and tell you.' : 'Free to cancel until 17:00 Thursday.')
            : D({ marginTop: 12 }, Btn(function () { v.act('book', [c[0], c[3] === 'full' ? 'waitlist' : 'booked']); }, { font: '500 14px/1 ' + sans, background: c[3] === 'full' ? 'transparent' : C.ink, color: c[3] === 'full' ? C.t1 : C.surf, border: c[3] === 'full' ? '1px solid rgba(23,23,26,.28)' : 'none', padding: '15px', borderRadius: 6, textAlign: 'center' }, c[3] === 'full' ? 'Join the waitlist' : 'Book it'))
        ]);
      })),
      D({ font: '400 12px/1.6 ' + sans, color: C.t2, marginTop: 16 }, 'Auto-booking from the waitlist is opt-in. Being charged for a class you did not know you got is a support ticket every time.')
    ]);
  };

  S['MBR-07'] = function (v) {
    var s2 = !!v.sets.m2;
    return mPage([
      D({ display: 'flex', gap: 10, alignItems: 'center' }, [
        D({ flex: 1 }, [D({ font: '500 19px/1.2 ' + sans, color: C.dT1 }, 'Lower body'), D({ font: '400 12px/1.5 ' + mono, color: C.dT3, marginTop: 3 }, '18 min · 2 of 5 exercises')]),
        Btn(function () { v.act('flash', 'Paused — resume any time today'); }, { font: '450 12px/1 ' + sans, color: C.dT1, border: '1px solid rgba(255,255,255,.24)', padding: '11px 12px', minHeight: 44, display: 'inline-flex', alignItems: 'center', borderRadius: 6 }, 'Pause')
      ]),
      D({ border: '1px solid ' + C.dLine, borderRadius: 6, background: C.dSurf, marginTop: 16, overflow: 'hidden' }, [
        D({ padding: '13px 14px', borderBottom: '1px solid rgba(255,255,255,.1)' }, [
          D({ font: '500 17px/1.3 ' + sans, color: C.dT1 }, 'Box squat'),
          D({ font: '400 12px/1.6 ' + sans, color: C.dT2, marginTop: 4 }, 'Yousef set this instead of a normal squat — easier on your knee.')
        ]),
        D({ padding: '4px 0' }, [
          D({ display: 'flex', gap: 12, alignItems: 'center', padding: '11px 14px', borderBottom: '1px solid rgba(255,255,255,.06)' }, [D({ font: '400 11px/1.4 ' + mono, color: C.dT3, width: 16 }, '1'), D({ font: '500 16px/1.2 ' + mono, color: C.dT1 }, '50.0 kg × 6'), D({ flex: 1 }), D({ font: '500 11px/1.4 ' + mono, color: C.dOk }, 'DONE')]),
          D({ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 14px', background: 'rgba(126,166,232,.12)', borderInlineStart: '2px solid ' + C.dAcc }, [
            D({ font: '400 11px/1.4 ' + mono, color: C.dAcc, width: 16 }, '2'),
            D({ font: '500 21px/1.2 ' + mono, color: C.dT1 }, '55.0 kg'),
            D({ flex: 1 }),
            s2 ? D({ font: '500 11px/1.4 ' + mono, color: C.dOk }, 'DONE')
              : Btn(function () { v.act('logSet', 'm2'); }, { font: '500 13px/1 ' + sans, background: C.dAcc, color: '#12233d', padding: '14px 18px', minHeight: 44, display: 'inline-flex', alignItems: 'center', borderRadius: 6 }, 'Done · 6')
          ]),
          [3, 4].map(function (n) {
            return D({ key: n, display: 'flex', gap: 12, alignItems: 'center', padding: '11px 14px', opacity: .5 }, [D({ font: '400 11px/1.4 ' + mono, color: C.dT3, width: 16 }, String(n)), D({ font: '500 16px/1.2 ' + mono, color: C.dT1 }, '55.0 kg × 6')]);
          })
        ]),
        D({ padding: '12px 14px', borderTop: '1px solid rgba(255,255,255,.1)', font: '400 12.5px/1.5 ' + sans, color: C.dT2 }, "Couldn't finish? Tap the weight to change it.")
      ]),
      s2 ? D({ border: '1px solid rgba(255,255,255,.12)', borderRadius: 6, background: C.dSurf, padding: '13px 14px', marginTop: 13 }, [
        D({ font: '500 13px/1.4 ' + sans, color: C.dT1 }, 'Rest · 1:24'),
        D({ height: 3, background: 'rgba(255,255,255,.1)', borderRadius: 2, marginTop: 9, overflow: 'hidden' }, D({ height: 3, width: '42%', background: C.dAcc })),
        D({ font: '400 11.5px/1.6 ' + sans, color: C.dT3, marginTop: 8 }, "Counts down as a number when you've turned motion off.")
      ]) : null,
      D({ marginTop: 14 }, Btn(function () { v.openScreen('MBR-08'); }, { font: '500 14px/1 ' + sans, background: C.dAcc, color: '#12233d', padding: '16px', borderRadius: 6, textAlign: 'center' }, 'Next exercise')),
      D({ font: '400 11px/1.5 ' + mono, color: C.dT3, marginTop: 11, textAlign: 'center' }, 'Saves offline · no coach needed')
    ], true);
  };

  S['MBR-08'] = function (v) {
    return mPage([
      D({ font: '500 30px/1.12 ' + sans, letterSpacing: '-.02em' }, 'Done.\n41 minutes.'),
      D({ font: '400 14.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 12 }, 'Five exercises, 18 sets. Your box squat is up 5kg since week 5.'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('PERSONAL BEST'),
        D({ font: '500 17px/1.3 ' + sans, marginTop: 6 }, 'Box squat · 55kg × 6'),
        D({ font: '400 12.5px/1.6 ' + sans, color: C.t2, marginTop: 5 }, 'Previous best 50kg × 6, three weeks ago.')
      ]), { marginTop: 18 }),
      D({ font: '400 13.5px/1.65 ' + sans, color: '#3d3b36', marginTop: 16 }, 'Next session Friday at 09:45 with Yousef.'),
      D({ marginTop: 16 }, sec('Back to today', function () { v.openScreen('MBR-01'); }, true))
    ]);
  };

  S['MBR-10'] = function (v) {
    var ate = !!v.meals.lunch;
    return mPage([
      D({ font: '500 26px/1.15 ' + sans, letterSpacing: '-.018em' }, "Today's food"),
      D({ font: '400 13px/1.5 ' + sans, color: C.t2, marginTop: 4 }, (ate ? '1,200' : '520') + ' of 2,150 kcal · ' + (ate ? '90' : '38') + 'g protein of 165g'),
      card(D({}, [
        ['BREAKFAST', 'Oats, banana, whey, almond butter', '520 kcal', true],
        ['LUNCH · 13:00', 'Chicken with rice and yoghurt', '680 kcal', ate],
        ['AFTER TRAINING · 18:15', 'Whey and dates', '310 kcal', false],
        ['DINNER · 20:30', 'Beef kofta, salad, flatbread', '640 kcal', false]
      ].map(function (m, i) {
        return Btn(function () { if (!m[3]) v.act('logMeal', i === 1 ? 'lunch' : 'other'); }, { key: i, padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', display: 'flex', gap: 11, alignItems: 'center', background: m[3] ? C.sunk : C.surf }, [
          D({ flex: 1 }, [eyebrow(m[0]), D({ font: '450 15px/1.4 ' + sans, marginTop: 3 }, m[1]), D({ font: '400 12px/1.5 ' + mono, color: C.t2, marginTop: 3 }, m[2])]),
          m[3] ? D({ font: '500 11px/1.4 ' + mono, color: C.ok }, 'EATEN') : D({ font: '500 12px/1 ' + sans, color: C.ink }, 'Ate it')
        ]);
      })), { marginTop: 16 }),
      D({ display: 'flex', gap: 9, marginTop: 14 }, [
        D({ flex: 1 }, sec('Search', function () { v.act('flash', 'Portions in plates and cups before grams'); }, true)),
        D({ flex: 1 }, sec('Photo', function () { v.act('flash', 'AI estimate, editable'); }, true)),
        D({ flex: 1 }, sec('Barcode', function () { v.act('flash', 'Scanning'); }, true))
      ]),
      D({ marginTop: 14 }, Btn(function () { v.act('flash', 'Grocery list — this week, by aisle'); }, { font: '400 13px/1.5 ' + sans, color: C.ink, minHeight: 44, display: 'flex', alignItems: 'center' }, 'My grocery list →'))
    ]);
  };

  S['MBR-23'] = function (v) {
    return mPage([
      D({ font: '400 13px/1.5 ' + sans, color: C.t2 }, 'Your membership'),
      D({ font: '500 28px/1.15 ' + sans, letterSpacing: '-.018em', marginTop: 2 }, 'Club'),
      D({ font: '400 14.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 8 }, 'JOD 55.00 a month · renews 21 August · Khalda'),
      card(D({}, [
        D({ padding: '14px 15px', borderBottom: '1px solid ' + C.hair }, [D({ font: '500 11px/1.5 ' + sans, color: C.t2 }, 'WHAT YOU GET'), D({ font: '400 14px/1.75 ' + sans, color: '#2c2a26', marginTop: 5 }, 'All opening hours at Khalda\nAll group classes\nGuest pass once a month')]),
        D({ padding: '14px 15px' }, [D({ font: '500 11px/1.5 ' + sans, color: C.t2 }, 'YOUR AGREEMENT'), D({ font: '400 14px/1.75 ' + sans, color: '#2c2a26', marginTop: 5 }, 'Started 4 March 2024\n12-month term, ends March 2026\nFrozen 1 month of 3 this year')])
      ]), { marginTop: 18 }),
      D({ marginTop: 16, padding: '14px 15px', background: C.sunk, borderRadius: 6, font: '400 13.5px/1.7 ' + sans, color: '#3d3b36' }, "If you cancel before March there's a two-month fee. Freezing is free and pauses everything."),
      D({ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 16 }, [
        sec('Freeze my membership', function () { v.act('flash', 'Freeze request sent to Khalda for approval'); }, true),
        sec('Change my plan', function () { v.act('flash', 'Club+ adds all clubs and 2 PT sessions — JOD 78.00'); }, true),
        Btn(function () { v.act('flash', 'A member of the team will call you within a day'); }, { font: '450 13.5px/1 ' + sans, color: C.t2, padding: '15px', textAlign: 'center' }, 'Cancel membership')
      ]),
      D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 14 }, 'Cancel is present, plainly worded, and last. Hiding it behind a phone call is the pattern members hate most and regulators increasingly forbid.')
    ]);
  };

  S['MBR-26'] = function (v) {
    if (v.payState === 'approved') {
      return mPage([
        D({ font: '500 28px/1.15 ' + sans, letterSpacing: '-.018em' }, 'Paid.'),
        D({ font: '400 14.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 10 }, 'JOD 55.00 by CliQ. Your receipt is on its way by WhatsApp, and your card on file has been replaced.'),
        D({ marginTop: 18 }, sec('Back to today', function () { v.act('payReset'); v.openScreen('MBR-01'); }, true))
      ]);
    }
    return mPage([
      D({ font: '500 26px/1.18 ' + sans, letterSpacing: '-.018em' }, 'Pay JOD 55.00'),
      D({ font: '400 14px/1.62 ' + sans, color: '#3d3b36', marginTop: 6 }, 'Your August membership. Your card ending 4417 expired, so pick another way.'),
      D({ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 18 }, [
        ['CliQ', 'From your bank app · instant', true],
        ['A different card', 'Saved for next month if you want', false],
        ['Pay at the desk', "Cash or card, next time you're in", false]
      ].map(function (m, i) {
        return Btn(function () { v.act('pay', 'approved'); }, { key: i, border: m[2] ? '2px solid ' + C.ink : '1px solid rgba(23,23,26,.18)', borderRadius: 6, padding: '15px 16px', background: m[2] ? '#f7f9fc' : C.surf }, [
          D({ font: '500 15.5px/1.35 ' + sans }, m[0]), D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 2 }, m[1])
        ]);
      })),
      D({ marginTop: 18 }, Btn(function () { v.act('pay', 'approved'); }, { font: '500 16px/1 ' + sans, background: C.ink, color: C.surf, padding: '19px', borderRadius: 6, textAlign: 'center' }, 'Pay with CliQ')),
      D({ marginTop: 16, padding: '13px 14px', background: C.sunk, borderRadius: 6, font: '400 13px/1.7 ' + sans, color: '#3d3b36' }, 'You can keep training either way — nothing is blocked. Your receipt arrives on WhatsApp.')
    ]);
  };

  // ---- reference view for every remaining registry row ----
  function reference(v) {
    var r = v.row;
    if (!r) return page([D({ font: '400 14px/1.6 ' + sans, color: C.t2 }, 'Loading the registry…')]);
    var mobile = r.surface === 'Veyro Coach' || r.surface === 'Veyro Member';
    var body = [
      D({}, [
        eyebrow(r.id + ' · ' + r.module + ' · ' + r.surface),
        D({ font: '500 ' + (mobile ? 20 : 24) + 'px/1.2 ' + sans, letterSpacing: '-.016em', marginTop: 8 }, r.name),
        D({ font: '400 13.5px/1.68 ' + sans, color: '#3d3b36', marginTop: 9, maxWidth: '76ch' }, r.note)
      ]),
      card(D({ padding: '14px 16px' }, [
        eyebrow('DRAWN, NOT YET WIRED'),
        D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26', marginTop: 7 }, 'This screen exists at production fidelity in the batch files, with its states, permission variants and annotations. It is reachable here and keeps its registry traceability, but it is not one of the interactive screens in this prototype — so the launcher counts it as a reference view rather than claiming it is live.'),
        D({ font: '400 11.5px/1.6 ' + mono, color: C.t2, marginTop: 10 }, 'ARABIC · ' + r.ar + '   ROLES · ' + r.roles)
      ])),
      card(D({ padding: '14px 16px' }, [
        eyebrow('WHERE TO GO FROM HERE'),
        D({ display: 'flex', gap: 8, marginTop: 9, flexWrap: 'wrap' }, [
          sec('Screen directory', function () { window.location.hash = '#/directory'; }),
          sec(mobile ? 'Back to Today' : 'Back to Command Center', function () { v.openScreen(mobile ? (r.surface === 'Veyro Coach' ? 'CCH-01' : 'MBR-01') : (r.surface === 'Internal Console' ? 'CON-01' : 'ADM-CC-01')); })
        ])
      ]))
    ];
    return mobile ? mPage(body) : page(body);
  }


  // ——— COACH: real screens, not reference pages ———
  S['CCH-04'] = function (v) {
    var rows = [
      ['Ahmad Nabulsi', '19 days since he trained', '4 credits', C.warn],
      ['Dana Qasem', 'Session today 11:00', '7 credits', null],
      ['Hala Barakat', 'Asked about her plan', '2 credits', C.warn],
      ['Yara Mansour', 'On track · week 5 of 12', '9 credits', null],
      ['Faris Alami', 'Nutrition check-in overdue', '5 credits', C.warn],
      ['Lina Haddad', 'On track · week 9 of 12', '3 credits', null]
    ];
    return mPage([
      h1('Your clients', '14 active · 3 need attention'),
      D({ display: 'flex', gap: 7, marginTop: 14, flexWrap: 'wrap' }, [
        Btn(function () {}, { font: "500 11.5px/1 " + sans, background: C.t1, color: C.surf, padding: '10px 12px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Needs attention'),
        sec('All 14', function () {}),
        sec('Today', function () {})
      ]),
      card(rows.map(function (r, i) {
        return Btn(function () { v.openScreen('CCH-05'); }, { display: 'flex', gap: 11, alignItems: 'center', padding: '13px 14px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ width: 34, height: 34, borderRadius: '50%', background: '#ece9e3', flexShrink: 0 }),
          D({ flex: 1, minWidth: 0 }, [
            D({ font: '500 14.5px/1.35 ' + sans }, r[0]),
            D({ font: '400 12px/1.5 ' + sans, color: r[3] || C.t2, marginTop: 2 }, r[1])
          ]),
          D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, r[2])
        ]);
      }), { marginTop: 14 })
    ]);
  };

  S['CCH-06'] = function (v) {
    return mPage([
      h1('Ahmad · 09:45', 'Lower body · week 8 of 12'),
      card(D({ padding: '14px 15px' }, [
        eyebrow('BEFORE HE ARRIVES', C.warn),
        D({ font: '400 13px/1.68 ' + sans, color: '#2c2a26', marginTop: 6 }, "19 days since his last session. He squatted 82.5 × 5 last time — don't open there."),
        D({ font: '400 12.5px/1.6 ' + sans, color: C.t2, marginTop: 8, paddingTop: 8, borderTop: '1px solid ' + C.hair }, 'Left knee, meniscus repair 2019. No deep loaded flexion.')
      ]), { marginTop: 14, borderColor: C.warn }),
      card(D({ padding: '14px 15px' }, [
        eyebrow("TODAY'S PLAN"),
        D({ font: '400 13.5px/1.9 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Box squat 4 × 6 · from 60kg\nRomanian deadlift 3 × 8\nLeg press 3 × 10\nWalking lunge 3 × 12\nCalf raise 4 × 15')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Start session', function () { v.openScreen('CCH-02'); }, true))
    ]);
  };

  S['CCH-07'] = function (v) {
    return mPage([
      h1('Session complete', 'Ahmad Nabulsi · 41 minutes'),
      card(D({ padding: '15px 16px' }, [
        D({ font: '400 13.5px/1.9 ' + sans, color: '#2c2a26' }, 'Box squat 55.0 × 6, 6, 5\nRomanian deadlift 90.0 × 8, 8\nLeg press 160 × 10, 10'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, 'Knee felt tight on set 2. Dropped to 55 rather than pushing.')
      ]), { marginTop: 14 }),
      card(D({ padding: '14px 15px' }, [
        eyebrow('WHAT THIS CONFIRMS'),
        D({ font: '400 13px/1.75 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Credit 7 of 10 used · 3 remaining\nAhmad sees the session in his app\nYour verification queue drops to 21')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Verify and close', function () { v.act('flash', 'Verified — 3 credits remaining, Ahmad notified'); }, true)),
      D({ marginTop: 9 }, sec('Book his next session', function () { v.openScreen('CCH-16'); }, true))
    ]);
  };

  S['CCH-09'] = function (v) {
    var ex = [['Box squat', 'Quads · barbell, box', true], ['Front squat', 'Quads · barbell', false], ['Leg press', 'Quads · machine', false], ['Split squat', 'Quads · dumbbell', false], ['Romanian deadlift', 'Hamstrings · barbell', false], ['Leg curl', 'Hamstrings · machine', false]];
    return mPage([
      h1('Add an exercise', 'Day A · lower body'),
      D({ marginTop: 12, font: '400 13.5px/1.5 ' + sans, color: C.t3, border: '1px solid ' + C.line, borderRadius: 6, padding: '12px 13px', minHeight: 44, display: 'flex', alignItems: 'center' }, 'Search movements'),
      D({ display: 'flex', gap: 7, marginTop: 11, flexWrap: 'wrap' }, [
        Btn(function () {}, { font: "500 11.5px/1 " + sans, background: C.t1, color: C.surf, padding: '10px 12px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Recent'),
        sec('Quads', function () {}), sec('Hamstrings', function () {}), sec('Available here', function () {})
      ]),
      card(ex.map(function (e, i) {
        return Btn(function () { v.act('flash', e[0] + ' added to Day A'); }, { display: 'flex', gap: 10, alignItems: 'center', padding: '13px 14px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ flex: 1 }, [D({ font: '450 14px/1.35 ' + sans }, e[0]), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, e[1])]),
          e[2] ? badge('SUBSTITUTE', C.warn) : null
        ]);
      }), { marginTop: 12 }),
      D({ font: '400 12px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Box squat is flagged as the substitute for a recorded knee limitation. Adding a deep-flexion movement will warn, not block.')
    ]);
  };

  S['CCH-11'] = function (v) {
    return mPage([
      h1('Ahmad · progress', 'Since March 2024'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WEIGHT'),
        D({ display: 'flex', alignItems: 'flex-end', gap: 4, height: 62, marginTop: 11 }, [82, 81, 81, 80, 79, 79, 78, 78].map(function (w, i) {
          return D({ key: i, flex: 1, height: ((w - 74) / 10 * 100) + '%', background: i > 5 ? '#57544d' : '#cbc6bc', borderRadius: 1 });
        })),
        D({ font: '400 12.5px/1.6 ' + sans, color: '#2c2a26', marginTop: 9 }, '78.4 kg · down 4.1 kg over 8 weigh-ins. Steady, not sharp.')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('STRENGTH'),
        D({ font: '400 13px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Box squat 55.0 × 6 · best\nRomanian deadlift 100 × 8\nLeg press 180 × 10')
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('PHOTOS'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 6 }, 'Ahmad has not shared progress photos. He controls that from his app and can withdraw it at any time.')
      ]), { marginTop: 12 })
    ]);
  };

  S['CCH-15'] = function (v) {
    var msgs = [['them', 'Sorry I missed last week, work has been heavy', '2d'], ['me', 'No problem at all. Shall we keep Wednesday 09:45 going forward?', '2d'], ['them', 'Yes that works', '2d'], ['them', 'Is the knee thing still a worry?', '1d']];
    return mPage([
      h1('Ahmad Nabulsi', 'Usually replies within a day'),
      D({ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 16 }, msgs.map(function (m, i) {
        var mine = m[0] === 'me';
        return D({ key: i, alignSelf: mine ? 'flex-end' : 'flex-start', maxWidth: '80%', background: mine ? C.wash : C.canvas, borderRadius: mine ? '8px 8px 2px 8px' : '8px 8px 8px 2px', padding: '11px 13px' }, [
          D({ font: '400 13px/1.62 ' + sans }, m[1]),
          D({ font: '400 10px/1.4 ' + mono, color: C.t2, marginTop: 4 }, m[2])
        ]);
      })),
      D({ marginTop: 16, display: 'flex', gap: 9, alignItems: 'center' }, [
        D({ flex: 1, font: '400 13px/1.5 ' + sans, color: C.t3, border: '1px solid ' + C.line, borderRadius: 6, padding: '12px 13px', minHeight: 44, display: 'flex', alignItems: 'center' }, 'Write a reply'),
        prim('Send', function () { v.act('flash', 'Sent to Ahmad'); })
      ])
    ]);
  };

  S['CCH-16'] = function (v) {
    var slots = [['Mon', '09:45 Ahmad', '17:30 Hala'], ['Tue', '11:00 Dana', ''], ['Wed', '09:45 Ahmad', '19:00 Spin'], ['Thu', '', '19:00 Spin'], ['Fri', '09:45 Ahmad', '11:00 Dana']];
    return mPage([
      h1('Your week', '9 sessions · 2 classes'),
      card(slots.map(function (s, i) {
        return D({ key: i, display: 'flex', gap: 11, padding: '13px 14px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '500 12px/1.4 ' + mono, color: C.t1, width: 34, flexShrink: 0 }, s[0]),
          D({ flex: 1 }, [
            s[1] ? D({ font: '450 13.5px/1.5 ' + sans }, s[1]) : D({ font: '400 12.5px/1.5 ' + sans, color: C.t3 }, 'Free'),
            s[2] ? D({ font: '450 13.5px/1.5 ' + sans, marginTop: 3 }, s[2]) : null
          ])
        ]);
      }), { marginTop: 14 }),
      D({ marginTop: 14 }, sec('Set your availability', function () { v.act('flash', 'Availability editor'); }, true))
    ]);
  };

  S['CCH-17'] = function (v) {
    var g = [['Ahmad Nabulsi', '6 sessions', '1–14 Aug'], ['Dana Qasem', '5 sessions', '3–17 Aug'], ['Hala Barakat', '4 sessions', '5–16 Aug'], ['Yara Mansour', '4 sessions', '8–18 Aug'], ['Faris Alami', '3 sessions', '11–18 Aug']];
    return mPage([
      h1('22 sessions to verify', 'Back to 1 August'),
      card(D({ padding: '13px 14px', background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, "Members can't see their remaining credits until you confirm these happened. Nothing is billed either.")), { marginTop: 14 }),
      card(g.map(function (r, i) {
        return D({ key: i, display: 'flex', gap: 11, alignItems: 'center', padding: '13px 14px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ flex: 1 }, [D({ font: '450 14px/1.35 ' + sans }, r[0]), D({ font: '400 11.5px/1.5 ' + mono, color: C.t2, marginTop: 2 }, r[2])]),
          D({ font: '400 12px/1.4 ' + mono, color: C.t2 }, r[1])
        ]);
      }), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Confirm all 22', function () { v.act('flash', 'All 22 verified — credits updated, members notified'); }, true)),
      D({ marginTop: 9 }, sec('Review one at a time', function () {}, true))
    ]);
  };

  S['CCH-18'] = function (v) {
    return mPage([
      h1('Yousef Haddad', 'Coach · Khalda'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('AVAILABILITY'),
        D({ font: '400 13px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Mon–Fri 08:00–18:00\nSaturday 09:00–13:00\nSunday closed')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('CERTIFICATIONS'),
        D({ font: '400 13px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'NASM CPT · expires March 2027\nFirst aid · expires November 2025')
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('LANGUAGE'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Arabic · your clients see Arabic by default')
      ]), { marginTop: 12 })
    ]);
  };


  // ——— MEMBER: real screens ———
  S['MBR-18'] = function (v) {
    var b = [['Spin', 'Thursday 19:00 · Dana', 'Studio 2', 'BOOKED', C.ok],
             ['Yoga', 'Saturday 10:00 · Nour', 'Studio 1', 'WAITLIST 2', C.warn],
             ['Spin', 'Last Thursday', 'Studio 2', 'ATTENDED', null]];
    return mPage([
      h1('Your bookings', '1 upcoming · 1 waitlisted'),
      card(b.map(function (r, i) {
        return Btn(function () { v.openScreen('MBR-17'); }, { display: 'flex', gap: 11, alignItems: 'center', padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ flex: 1, minWidth: 0 }, [
            D({ font: '500 15px/1.35 ' + sans }, r[0]),
            D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 2 }, r[1] + ' · ' + r[2])
          ]),
          r[4] ? badge(r[3], r[4]) : D({ font: '400 10px/1.4 ' + mono, color: C.t3 }, r[3])
        ]);
      }), { marginTop: 14 }),
      D({ marginTop: 14 }, prim('Book something else', function () { v.openScreen('MBR-03'); }, true))
    ]);
  };

  S['MBR-17'] = function (v) {
    return mPage([
      h1('Spin with Dana', 'Thursday 19:00'),
      card(D({ padding: '15px 16px' }, [
        D({ font: '400 14px/1.85 ' + sans, color: '#2c2a26' }, 'Studio 2, Khalda\nBike 7 held for you\n45 minutes'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, 'Bring water and a towel. Arrive five minutes early — bikes are released at 19:00.')
      ]), { marginTop: 14 }),
      card(D({ padding: '14px 15px', background: C.sunk }, D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26' }, 'Free to cancel until 17:00 Thursday. After that it counts as attended.')), { marginTop: 12 }),
      D({ marginTop: 16 }, sec('Add to my calendar', function () { v.act('flash', 'Added'); }, true)),
      D({ marginTop: 9 }, Btn(function () { v.openScreen('MBR-20'); }, { font: '450 13.5px/1 ' + sans, color: C.t2, minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'center' }, 'Cancel this booking'))
    ]);
  };

  S['MBR-20'] = function (v) {
    return mPage([
      h1('Cancel Spin?', 'Thursday 19:00 with Dana'),
      card(D({ padding: '15px 16px' }, D({ font: '400 14px/1.75 ' + sans, color: '#2c2a26' }, "You're inside the free window — cancelling now costs nothing and your bike goes to the next person on the waitlist.")), { marginTop: 14 }),
      D({ marginTop: 16 }, prim('Yes, cancel it', function () { v.act('flash', 'Cancelled · bike offered to the waitlist'); v.openScreen('MBR-18'); }, true)),
      D({ marginTop: 9 }, sec('Keep my booking', function () { v.openScreen('MBR-17'); }, true))
    ]);
  };

  S['MBR-19'] = function (v) {
    return mPage([
      h1('Saturday Yoga', "You're second on the list"),
      card(D({ padding: '15px 16px' }, [
        D({ font: '400 14px/1.75 ' + sans, color: '#2c2a26' }, 'Two people ahead of you. Places usually open up — nine of the last ten waitlists at this class cleared by the morning of.'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, "We'll book you automatically and let you know. You can turn that off if you'd rather decide yourself.")
      ]), { marginTop: 14 }),
      D({ marginTop: 16 }, sec('Book me automatically · on', function () { v.act('flash', 'Auto-book stays on'); }, true)),
      D({ marginTop: 9 }, Btn(function () { v.openScreen('MBR-18'); }, { font: '450 13.5px/1 ' + sans, color: C.t2, minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'center' }, 'Leave the waitlist'))
    ]);
  };

  S['MBR-22'] = function (v) {
    return mPage([
      h1('Your progress', 'Since March 2024'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WEIGHT'),
        D({ font: '500 26px/1.15 ' + mono, marginTop: 7 }, '78.4 kg'),
        D({ display: 'flex', alignItems: 'flex-end', gap: 4, height: 56, marginTop: 12 }, [82, 81, 81, 80, 79, 79, 78, 78].map(function (w, i) {
          return D({ key: i, flex: 1, height: ((w - 74) / 10 * 100) + '%', background: i > 5 ? '#57544d' : '#cbc6bc', borderRadius: 1 });
        })),
        D({ font: '400 13px/1.65 ' + sans, color: '#2c2a26', marginTop: 10 }, 'Down 4.1 kg since March. Steady rather than sharp, which is what Yousef was aiming for.')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT YOU CAN LIFT'),
        D({ font: '400 14px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Box squat 55.0 kg × 6\nRomanian deadlift 100 kg × 8\nLeg press 180 kg × 10')
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('PHOTOS'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Private to you. Share with Yousef whenever you like — you can stop sharing at any point.'),
        D({ marginTop: 12 }, sec('Take a progress photo', function () { v.act('flash', 'Camera'); }, true))
      ]), { marginTop: 12 })
    ]);
  };

  S['MBR-24'] = function (v) {
    return mPage([
      h1('Freeze your membership', 'Club · JOD 55.00 a month'),
      card(D({ padding: '15px 16px' }, [
        D({ font: '400 14px/1.8 ' + sans, color: '#2c2a26' }, "While frozen you won't be charged and won't be able to train. Your price stays the same when you come back."),
        D({ font: '400 13px/1.7 ' + sans, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, "You've used 1 of 3 freeze months this year.")
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('HOW LONG'),
        D({ display: 'flex', gap: 8, marginTop: 9, flexWrap: 'wrap' }, [
          Btn(function () {}, { font: "500 13px/1 " + sans, background: C.t1, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, '1 month'),
          sec('2 months', function () {}, true)
        ]),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 11 }, 'Frozen 1 September to 30 September. Billing restarts 1 October.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Ask Khalda to freeze it', function () { v.act('flash', 'Request sent — Khalda usually replies same day'); }, true)),
      D({ font: '400 12px/1.6 ' + sans, color: C.t2, marginTop: 10 }, 'Your club approves freezes, so this is a request rather than an instant change.')
    ]);
  };

  S['MBR-25'] = function (v) {
    var inv = [['August', 'JOD 55.00', 'NOT PAID YET', C.err], ['July', 'JOD 55.00', 'Paid 1 Jul', null], ['June', 'JOD 55.00', 'Paid 1 Jun', null], ['PT · 10 sessions', 'JOD 280.00', 'Paid 14 Jan', null]];
    return mPage([
      h1('Payments', 'Club membership · Khalda'),
      card(inv.map(function (r, i) {
        return Btn(function () { v.act('flash', 'Receipt for ' + r[0]); }, { display: 'flex', gap: 11, alignItems: 'center', padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ flex: 1, minWidth: 0 }, [
            D({ font: '450 14.5px/1.35 ' + sans }, r[0]),
            D({ font: '400 12px/1.5 ' + sans, color: r[3] || C.t2, marginTop: 2 }, r[2])
          ]),
          D({ font: '500 13.5px/1.2 ' + mono, color: r[3] || C.t1 }, r[1])
        ]);
      }), { marginTop: 14 }),
      D({ marginTop: 16 }, prim('Pay August · JOD 55.00', function () { v.openScreen('MBR-26'); }, true)),
      D({ marginTop: 9 }, sec('Download receipts', function () { v.act('flash', 'Receipts sent to your email'); }, true))
    ]);
  };

  S['MBR-27'] = function (v) {
    return mPage([
      h1('How you pay', ''),
      card(D({ padding: '15px 16px' }, [
        D({ display: 'flex', gap: 10, alignItems: 'center' }, [
          D({ flex: 1 }, [D({ font: '500 15px/1.35 ' + sans }, 'Visa ···4417'), D({ font: '400 12.5px/1.5 ' + sans, color: C.err, marginTop: 2 }, 'Expired July 2026')]),
          badge('EXPIRED', C.err)
        ]),
        D({ marginTop: 12 }, prim('Replace this card', function () { v.act('flash', 'Card form'); }, true))
      ]), { marginTop: 14, borderColor: C.err }),
      card(D({ padding: '15px 16px' }, [
        D({ font: '400 13.5px/1.75 ' + sans, color: '#2c2a26' }, "Add a second way to pay and we'll use it if the first one fails — most missed payments are just an expired card."),
        D({ marginTop: 12 }, sec('Add another card', function () { v.act('flash', 'Card form'); }, true))
      ]), { marginTop: 12 })
    ]);
  };

  S['MBR-29'] = function (v) {
    return mPage([
      D({ font: '500 22px/1.2 ' + sans, letterSpacing: '-.016em' }, 'Your pass'),
      D({ font: '400 13px/1.6 ' + sans, color: C.t2, marginTop: 4 }, 'Hold this at the turnstile'),
      D({ marginTop: 20, background: C.surf, border: '1px solid ' + C.line, borderRadius: 8, padding: 24, textAlign: 'center' }, [
        D({ width: 168, height: 168, margin: '0 auto', background: 'repeating-linear-gradient(0deg,#17171a 0 6px,#fffefb 6px 12px),repeating-linear-gradient(90deg,#17171a 0 6px,#fffefb 6px 12px)', backgroundBlendMode: 'difference', borderRadius: 4 }),
        D({ font: '500 14px/1.4 ' + mono, marginTop: 16 }, 'M-04188'),
        D({ font: '400 12px/1.5 ' + sans, color: C.t2, marginTop: 5 }, 'Ahmad Nabulsi · Club')
      ]),
      card(D({ padding: '14px 15px', background: C.sunk }, D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26' }, "This works without a signal. If the turnstile won't read it, the front desk can let you in.")), { marginTop: 16 })
    ]);
  };

  S['MBR-31'] = function (v) {
    var n = [['Your card expired', 'August payment did not go through', '2h', 'MBR-26'],
             ['Yousef sent you a message', 'About your knee', '1d', 'MBR-30'],
             ['Spin confirmed', 'Thursday 19:00, bike 7', '2d', 'MBR-17'],
             ['You hit a new best', 'Box squat 55 kg × 6', '3w', 'MBR-22']];
    return mPage([
      h1('Notifications', ''),
      card(n.map(function (r, i) {
        return Btn(function () { v.openScreen(r[3]); }, { display: 'flex', gap: 11, alignItems: 'flex-start', padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ flex: 1, minWidth: 0 }, [
            D({ font: '450 14.5px/1.35 ' + sans }, r[0]),
            D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 2 }, r[1])
          ]),
          D({ font: '400 10.5px/1.4 ' + mono, color: C.t3 }, r[2])
        ]);
      }), { marginTop: 14 })
    ]);
  };

  S['MBR-32'] = function (v) {
    return mPage([
      h1('Ahmad Nabulsi', 'Member since March 2024'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT YOU WANT'),
        D({ font: '400 14px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Lose weight · train 4 days a week')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('FOOD'),
        D({ font: '400 14px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'No fish\nLactose sensitive'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9 }, 'Yousef builds your plans around this. Change it here and your next plan follows.')
      ]), { marginTop: 12 }),
      card([
        Btn(function () { v.openScreen('MBR-33'); }, { display: 'flex', padding: '15px 16px', minHeight: 44, alignItems: 'center' }, D({ font: '450 14.5px/1.35 ' + sans, flex: 1 }, 'Password and unlock')),
        Btn(function () { v.openScreen('MBR-34'); }, { display: 'flex', padding: '15px 16px', borderTop: '1px solid ' + C.hair, minHeight: 44, alignItems: 'center' }, D({ font: '450 14.5px/1.35 ' + sans, flex: 1 }, 'Privacy and what you share'))
      ], { marginTop: 12 })
    ]);
  };

  S['MBR-33'] = function (v) {
    return mPage([
      h1('Password and unlock', ''),
      card([
        D({ padding: '15px 16px' }, [D({ font: '450 14.5px/1.35 ' + sans }, 'Face unlock'), D({ font: '400 12.5px/1.5 ' + sans, color: C.ok, marginTop: 3 }, 'On')]),
        D({ padding: '15px 16px', borderTop: '1px solid ' + C.hair }, [D({ font: '450 14.5px/1.35 ' + sans }, 'Change password'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 3 }, 'Last changed 11 months ago')])
      ], { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHERE YOU ARE SIGNED IN'),
        D({ font: '400 13.5px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'iPhone · Amman · now\niPad · Amman · 3 weeks ago'),
        D({ marginTop: 12 }, sec('Sign out everywhere else', function () { v.act('flash', 'Signed out of 1 other device'); }, true))
      ]), { marginTop: 12 })
    ]);
  };

  S['MBR-34'] = function (v) {
    var rows = [['Offers and news', 'Off', 'You turned this off in July'], ['Yousef can see your food log', 'On', 'He uses it to adjust your plan'], ['Yousef can see your photos', 'Off', 'Nothing shared yet'], ['Health details', 'On', 'Only your coach and the club']];
    return mPage([
      h1('Privacy', 'What you share, and with whom'),
      card(rows.map(function (r, i) {
        return D({ key: i, padding: '15px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ display: 'flex', gap: 10, alignItems: 'center' }, [
            D({ font: '450 14.5px/1.35 ' + sans, flex: 1 }, r[0]),
            D({ font: '500 12px/1.4 ' + mono, color: r[1] === 'On' ? C.ok : C.t2 }, r[1])
          ]),
          D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 3 }, r[2])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        D({ font: '400 13.5px/1.75 ' + sans, color: '#2c2a26' }, 'You can ask for a copy of everything we hold about you, or ask us to delete your account.'),
        D({ marginTop: 12 }, sec('Request my data', function () { v.act('flash', 'Request logged — 30 days'); }, true))
      ]), { marginTop: 12 })
    ]);
  };


  S['FD-02'] = function (v) {
    var m = [['Ahmad Nabulsi', 'Club · Khalda', 'OWES JOD 55.00', C.warn], ['Ahmad Sabbagh', 'Flex · Khalda', 'Active', null], ['Ahmed Nabhan', 'Club+ · Abdoun', 'Other club', C.info]];
    return tPage([
      h1('Find a member', 'Nothing scanned — search instead'),
      D({ marginTop: 14, border: '2px solid ' + C.ink, borderRadius: 6, background: C.surf, padding: '15px 17px' }, [
        eyebrow('NAME, PHONE OR MEMBER ID', C.ink),
        D({ font: '400 19px/1.3 ' + sans, marginTop: 9 }, 'ahmad n')
      ]),
      card(m.map(function (r, i) {
        return Btn(function () { v.openScreen('ADM-MEM-01'); }, { display: 'flex', gap: 12, alignItems: 'center', padding: '15px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 48 }, [
          D({ width: 38, height: 38, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
          D({ flex: 1, minWidth: 0 }, [D({ font: '500 15.5px/1.35 ' + sans }, r[0]), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, r[1])]),
          r[3] ? badge(r[2], r[3]) : D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, r[2])
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Photos are shown so you confirm the person in front of you, not just the name. Three Ahmads is normal at this size.')
    ]);
  };

  S['FD-03'] = function (v) {
    return tPage([
      D({ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 200 }, [D({ font: '500 24px/1.18 ' + sans, letterSpacing: '-.016em' }, 'Tareq was turned away'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 4 }, 'Turnstile 2 · 18:39 · membership ended 7 August')]),
        badge('DENIED', C.err)
      ]),
      card(D({ padding: '16px 17px' }, [
        D({ font: '400 14.5px/1.7 ' + sans, color: '#2c2a26' }, "His membership ended twelve days ago and the grace period ran out five days ago. He was here three times a week for two years."),
        D({ font: '400 13px/1.65 ' + sans, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, 'You can let him in — it records who authorised it and why.')
      ]), { marginTop: 14, borderColor: C.err }),
      D({ display: 'flex', gap: 9, marginTop: 16, flexWrap: 'wrap' }, [
        prim('Renew · Flex JOD 40.00', function () { v.openScreen('POS-04'); }, true),
        sec('One-day pass · 8.00', function () { v.openScreen('POS-01'); }, true),
        sec('Let him in and flag it', function () { v.act('flash', 'Entry recorded against your name · flagged for a call'); }, true)
      ])
    ]);
  };

  S['FD-04'] = function (v) {
    return tPage([
      h1('Guest entry', 'Day pass · JOD 8.00'),
      card(D({ padding: '16px 17px' }, [
        eyebrow('WHO'),
        D({ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }, [
          field('Name', 'Sara Halabi'), field('Phone', '079 555 0134'), field('Date of birth', '14 / 03 / 1994')
        ])
      ]), { marginTop: 14 }),
      card(D({ padding: '16px 17px' }, [
        eyebrow('WAIVER'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Version 4, June 2026. She reads and accepts it on the tablet — the version she accepted is stored with her record.'),
        D({ marginTop: 12 }, sec('Hand her the tablet', function () { v.act('flash', 'Waiver accepted · v4'); }, true))
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Take payment · JOD 8.00', function () { v.openScreen('POS-01'); }, true))
    ]);
  };

  S['FD-05'] = function (v) {
    return tPage([
      h1('Start a trial', 'Seven days, free'),
      card(D({ padding: '16px 17px' }, [
        D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26' }, 'Two things and she can train today. Everything else the sales team collects later.'),
        D({ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 13 }, [field('Name', 'Rana Sabbagh'), field('Phone', '079 411 0288')])
      ]), { marginTop: 14 }),
      D({ marginTop: 16 }, prim('Start her trial', function () { v.act('flash', 'Trial started · day 1 of 7 · pass issued'); v.openScreen('ADM-CRM-05'); }, true)),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'This creates her real member record. When she joins, nothing is typed again — the trial becomes the membership.')
    ]);
  };

  S['FD-06'] = function (v) {
    var r = [['Dana Qasem', 'Arrived 18:41', true], ['Hala Barakat', 'Arrived 18:44', true], ['Lina Haddad', 'Not here yet', false], ['Omar Zaid', 'Not here yet', false], ['Faris Alami', 'Waitlist · promoted', false]];
    return tPage([
      h1('Spin · 19:00', 'Studio 2 · 18 booked · 12 arrived'),
      card(r.map(function (x, i) {
        return Btn(function () { v.act('flash', x[1] === 'Not here yet' ? x[0] + ' checked in' : x[0] + ' already in'); }, { display: 'flex', gap: 12, alignItems: 'center', padding: '14px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 48, background: x[2] ? C.sunk : 'transparent' }, [
          D({ width: 32, height: 32, borderRadius: '50%', background: '#ece9e3', flexShrink: 0 }),
          D({ flex: 1, minWidth: 0 }, [D({ font: '450 15px/1.35 ' + sans }, x[0]), D({ font: '400 12px/1.5 ' + mono, color: C.t2, marginTop: 2 }, x[1])]),
          x[2] ? D({ font: '500 11px/1.4 ' + mono, color: C.ok }, 'IN') : sec('Check in', function () {})
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Bikes are released at 18:55. Faris came off the waitlist when Nour cancelled.')
    ]);
  };

  S['FD-07'] = function (v) {
    return tPage([
      h1('Closing your shift', '16:00 – 22:00 · Layla'),
      card(D({ padding: '16px 17px' }, [
        row('Card payments', 'JOD 188.50'), row('Cash taken', 'JOD 96.00'), row('Opening float', 'JOD 50.00'),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 11, paddingTop: 11, borderTop: '1px solid ' + C.line }, [
          D({ font: '500 14.5px/1.4 ' + sans }, 'Cash expected'), D({ font: '500 18px/1.15 ' + mono }, 'JOD 146.00')
        ])
      ]), { marginTop: 14 }),
      card(D({ padding: '16px 17px' }, [
        eyebrow('WHAT YOU COUNTED'),
        D({ font: '500 24px/1.15 ' + mono, marginTop: 9 }, 'JOD 146.00'),
        D({ font: '400 12.5px/1.6 ' + sans, color: C.ok, marginTop: 7 }, 'Matches. No note needed.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Close and hand over', function () { v.act('flash', 'Shift closed · report sent to Ziad'); }, true))
    ]);
  };

  S['FD-08'] = function (v) {
    var dev = [['Card reader', 'Connected', C.ok], ['Receipt printer', 'Connected', C.ok], ['Turnstile 1', 'Connected', C.ok], ['Turnstile 2', 'Not responding', C.err], ['Barcode scanner', 'Connected', C.ok]];
    return tPage([
      h1('Your equipment', 'One thing needs attention'),
      card(dev.map(function (x, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '15px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '450 15px/1.35 ' + sans, flex: 1 }, x[0]),
          D({ font: '500 12px/1.4 ' + mono, color: x[2] }, x[1])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26' }, 'Turnstile 2 stopped responding at 09:04. Members can still come in through turnstile 1 or check in here at the desk — nothing is lost.')), { marginTop: 12, borderColor: C.err }),
      D({ marginTop: 14 }, sec('Tell maintenance', function () { v.act('flash', 'Reported · ticket #2841'); }, true))
    ]);
  };

  S['FD-09'] = function (v) {
    return tPage([
      D({ display: 'flex', gap: 11, padding: '14px 16px', background: '#f4ece5', border: '1px solid rgba(138,90,31,.4)', borderRadius: 6, alignItems: 'flex-start' }, [
        D({ width: 3, alignSelf: 'stretch', background: C.warn, flexShrink: 0 }),
        D({ flex: 1 }, [
          D({ font: '500 15px/1.35 ' + sans }, 'No connection · you can keep working'),
          D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26', marginTop: 4 }, "Check-in works from what's already on this machine. Cash and CliQ sales record normally. Card sales queue and go through when the connection returns."),
          D({ font: '400 11.5px/1.5 ' + mono, color: C.t2, marginTop: 8 }, 'Offline 6 minutes · 2 sales queued · retrying')
        ])
      ]),
      h1('Khalda · front desk', 'Wednesday 18:47'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT STILL WORKS'),
        D({ font: '400 13.5px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Member check-in · from cached records\nCash and CliQ sales\nClass rosters for today'),
        D({ font: '500 9.5px/1.4 ' + mono, color: C.warn, letterSpacing: '.07em', marginTop: 12 }, "WHAT DOESN'T"),
        D({ font: '400 13.5px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Card payments · queued, not taken\nNew memberships\nAnything about other clubs')
      ]), { marginTop: 14 })
    ]);
  };

  S['POS-04'] = function (v) {
    return tPage([
      h1('Sell a membership', 'Tareq Odeh · renewing'),
      card([
        planRow('Flex', 'Off-peak · no classes', 'JOD 40.00', true),
        planRow('Club', 'All hours · classes included', 'JOD 55.00', false),
        planRow('Club+', 'All clubs · 2 PT monthly', 'JOD 78.00', false)
      ], { marginTop: 14 }),
      card(D({ padding: '15px 16px', background: C.sunk }, [
        row('Today', 'JOD 40.00'), row('Then monthly from 1 Sep', 'JOD 40.00'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9, paddingTop: 9, borderTop: '1px solid ' + C.hair }, 'Monthly rolling. He can stop any time with 30 days notice — no commitment fee.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Take payment · JOD 40.00', function () { v.openScreen('POS-02'); }, true))
    ]);
  };

  S['POS-05'] = function (v) {
    return tPage([
      h1('Personal training', 'Ahmad Nabulsi'),
      card([
        planRow('5 sessions', 'Use within 3 months', 'JOD 150.00', false),
        planRow('10 sessions', 'Use within 6 months · best value', 'JOD 280.00', true),
        planRow('20 sessions', 'Use within 12 months', 'JOD 520.00', false)
      ], { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WITH WHICH COACH'),
        D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Yousef Haddad · he already trains Ahmad'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 8 }, 'Credits appear on Ahmad\u2019s record straight away and Yousef sees them.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Take payment · JOD 280.00', function () { v.openScreen('POS-02'); }, true))
    ]);
  };

  S['POS-06'] = function (v) {
    return tPage([
      h1('Refund', 'Whey 1kg · sold 2 hours ago'),
      card(D({ padding: '16px 17px' }, [
        row('Original sale', 'JOD 28.00'), row('Paid by', 'Visa ···4417'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 11, paddingTop: 11, borderTop: '1px solid ' + C.hair }, 'This goes back to the same card. It usually takes three to five days to appear.')
      ]), { marginTop: 14 }),
      card(D({ padding: '16px 17px' }, [
        eyebrow('A MANAGER HAS TO APPROVE THIS', C.err),
        D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Ziad is on shift. He approves on his own screen — you do not need his password.'),
        D({ marginTop: 12 }, prim('Ask Ziad to approve', function () { v.act('flash', 'Sent to Ziad · waiting'); }, true))
      ]), { marginTop: 12, borderColor: C.err })
    ]);
  };

  S['POS-07'] = function (v) {
    return tPage([
      h1('Receipt', 'Sale 20419 · JOD 60.72'),
      card(D({ padding: '18px 19px', background: C.surf }, [
        D({ font: '500 14px/1.4 ' + sans, textAlign: 'center' }, 'Nadi Group · Khalda'),
        D({ font: '400 11px/1.5 ' + mono, color: C.t2, textAlign: 'center', marginTop: 3 }, 'Tax no. 1099238471'),
        D({ marginTop: 14, paddingTop: 14, borderTop: '1px solid ' + C.hair }, [
          row('Water 500ml × 2', '1.00'), row('Protein bar', '2.00'), row('Club membership · August', '55.00'), row('Sales tax 16% on retail', '2.72')
        ]),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 12, paddingTop: 12, borderTop: '1px solid ' + C.line }, [
          D({ font: '500 14.5px/1.4 ' + sans }, 'Total'), D({ font: '500 18px/1.15 ' + mono }, 'JOD 60.72')
        ]),
        D({ font: '400 11px/1.6 ' + mono, color: C.t2, marginTop: 12 }, 'Card ···4417 · 19 Aug 18:52\nJoFotara ref JO-2026-0819-4471')
      ]), { marginTop: 14 }),
      D({ display: 'flex', gap: 9, marginTop: 16, flexWrap: 'wrap' }, [
        prim('Print', function () { v.act('flash', 'Printing'); }, true),
        sec('Send by WhatsApp', function () { v.act('flash', 'Sent to Ahmad'); }, true),
        sec('Email it', function () { v.act('flash', 'Sent'); }, true)
      ])
    ]);
  };


  S['CON-03'] = function (v) {
    return dPage([
      h1('Nadi Group', 'Growth · 3 clubs · Amman, Jordan'),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('MRR', 'JOD 2,400.00', 'since June 2026'),
        metric('MEMBERS', '4,812', 'across 3 clubs'),
        metric('HEALTH', 'Good', 'no open incidents'),
        metric('VERSION', '4.18.2', 'current')
      ]),
      card(D({ padding: '15px 16px' }, [
        eyebrow('RECENT'),
        D({ font: '400 13px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, '18 authorisation failures during the provider incident\n3 JoFotara rejections, all corrected\nMember import completed 14 June')
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Counts only. No member names, phone numbers or payment details are on this screen — opening their data needs an impersonation session with a stated reason.')), { marginTop: 12 }),
      D({ display: 'flex', gap: 9, marginTop: 14, flexWrap: 'wrap' }, [
        sec('Subscription', function () { v.openScreen('CON-06'); }),
        sec('Usage', function () { v.openScreen('CON-07'); }),
        sec('Open their data', function () { v.openScreen('CON-09'); })
      ])
    ]);
  };

  S['CON-04'] = function (v) {
    return dPage([
      h1('New tenant', 'Provisioning'),
      card(D({ padding: '16px 17px' }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Organisation', 'Pulse Amman'),
        field('Region', 'Jordan · data stays in-region'),
        field('Plan', 'Starter · 1 club, 500 members'),
        field('First administrator', 'rana@pulseamman.jo')
      ])), { marginTop: 14 }),
      card(D({ padding: '15px 16px', borderColor: C.warn }, [
        eyebrow('REGION CANNOT BE CHANGED LATER', C.warn),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Region sets where their data lives and which tax adapter they get — JoFotara for Jordan. Moving a tenant afterwards means a migration, not a setting.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Create and invite Rana', function () { v.act('flash', 'Tenant created · invitation sent'); v.openScreen('CON-02'); }, true))
    ]);
  };

  S['CON-05'] = function (v) {
    var e = [['Missing join date', 18, 'Use their first payment date'], ['Duplicate phone number', 6, 'Merge into one record'], ['Unrecognised plan name', 3, 'Map to an existing plan']];
    return dPage([
      h1('Member import', 'Pulse Amman · 1,284 rows'),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('IMPORTED', '1,257', 'clean, already live'),
        metric('WAITING', '27', 'need a decision'),
        metric('REJECTED', '0', '')
      ]),
      card(e.map(function (x, i) {
        return D({ key: i, padding: '14px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }, [
          D({ flex: 1, minWidth: 180 }, [D({ font: '450 13.5px/1.4 ' + sans }, x[0]), D({ font: '400 12px/1.55 ' + sans, color: C.t2, marginTop: 2 }, x[2])]),
          D({ font: '500 13px/1.2 ' + mono, color: C.warn }, x[1] + ' rows'),
          sec('Apply to all ' + x[1], function () { v.act('flash', x[1] + ' rows resolved'); })
        ]);
      }), { marginTop: 12 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'The clean 1,257 are already in and usable. These 27 wait rather than blocking the rest.')
    ]);
  };

  S['CON-06'] = function (v) {
    return dPage([
      h1('Subscription', 'Nadi Group · Growth'),
      card(D({ padding: '16px 17px' }, [
        row('Plan', 'Growth'), row('Clubs', '3 of 5'), row('Members', '4,812 of 10,000'), row('Monthly', 'JOD 2,400.00'), row('Renews', '1 September 2026')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT THEY HAVE'),
        D({ font: '400 13px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Nutrition coaching · on\nAutomations · on\nWhite-label branding · on\nAPI access · off')
      ]), { marginTop: 12 }),
      D({ marginTop: 14 }, sec('Change their plan', function () { v.act('flash', 'Plan change · states what they gain or lose'); }, true))
    ]);
  };

  S['CON-07'] = function (v) {
    var u = [['Members', 4812, 10000], ['Clubs', 3, 5], ['Staff accounts', 24, 50], ['WhatsApp messages this month', 8412, 15000], ['Storage', 41, 100]];
    return dPage([
      h1('Usage', 'Nadi Group · August'),
      card(u.map(function (x, i) {
        var pct = Math.round(x[1] / x[2] * 100);
        return D({ key: i, padding: '14px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ display: 'flex', gap: 10, alignItems: 'baseline' }, [
            D({ font: '450 13.5px/1.4 ' + sans, flex: 1 }, x[0]),
            D({ font: '500 12.5px/1.2 ' + mono }, x[1].toLocaleString() + ' / ' + x[2].toLocaleString()),
            D({ font: '400 11px/1.4 ' + mono, color: pct > 80 ? C.warn : C.t2, width: 40, textAlign: 'end' }, pct + '%')
          ]),
          D({ height: 3, background: '#ece9e3', marginTop: 6, borderRadius: 2, overflow: 'hidden' }, D({ height: 3, width: pct + '%', background: pct > 80 ? C.warn : '#57544d' }))
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Nothing near a limit. When something passes 80% it raises an internal task rather than an unexpected invoice.')
    ]);
  };

  S['CON-08'] = function (v) {
    var t = [['08:52', 'First failed authorisation, Nadi Group'], ['08:54', 'Threshold crossed, incident opened automatically'], ['09:01', 'Provider confirmed degraded service'], ['09:06', 'Three affected tenants notified'], ['09:31', 'Authorisations recovering'], ['09:44', 'All queued payments submitted, none charged twice']];
    return dPage([
      D({ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 220 }, [D({ font: '500 24px/1.18 ' + sans, letterSpacing: '-.016em' }, 'Payment provider degraded'), D({ font: '400 12.5px/1.5 ' + sans, color: C.t2, marginTop: 4 }, '19 August · 52 minutes · 3 tenants · 41 authorisations')]),
        badge('RESOLVED', C.ok)
      ]),
      card(t.map(function (x, i) {
        return D({ key: i, display: 'flex', gap: 12, padding: '11px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '400 11px/1.5 ' + mono, color: C.t2, width: 44, flexShrink: 0 }, x[0]),
          D({ font: '400 12.5px/1.6 ' + sans, flex: 1 }, x[1])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT WE TOLD THEM'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, '"Card payments are failing intermittently. Cash, CliQ and check-in are unaffected. Nothing has been double-charged and failed payments will retry automatically."')
      ]), { marginTop: 12 })
    ]);
  };

  S['CON-10'] = function (v) {
    var f = [['Nutrition photo logging', 'All tenants', C.ok], ['New booking engine', '15% of tenants', C.warn], ['API access', 'Enterprise only', C.info], ['Arabic Coach app', 'Nadi Group only', C.warn]];
    return dPage([
      h1('Feature flags', '4 active rollouts'),
      card(f.map(function (x, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '14px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', flexWrap: 'wrap' }, [
          D({ font: '450 13.5px/1.4 ' + sans, flex: 1, minWidth: 160 }, x[0]),
          D({ font: '400 12px/1.4 ' + mono, color: x[2] }, x[1]),
          sec('Kill', function () { v.act('flash', x[0] + ' disabled everywhere'); })
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Anything touching money or access needs a second approver before it changes. Every change is logged with who and why.')), { marginTop: 12 })
    ]);
  };

  S['CON-11'] = function (v) {
    var s = [['Web application', 'Healthy', C.ok], ['Payments', 'Healthy', C.ok], ['JoFotara submission queue', '3 waiting', C.warn], ['Access hardware sync', 'Healthy', C.ok], ['WhatsApp delivery', 'Healthy', C.ok], ['Search index', 'Healthy', C.ok]];
    return dPage([
      h1('System health', 'All regions'),
      card(s.map(function (x, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '450 13.5px/1.4 ' + sans, flex: 1 }, x[0]),
          D({ font: '500 12px/1.4 ' + mono, color: x[2] }, x[1])
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'The JoFotara queue holds three invoices that were rejected for a missing buyer tax number. They resubmit once the field is corrected — not a system fault.')
    ]);
  };

  S['CON-12'] = function (v) {
    var a = [['09:12', 'Support · impersonation started', 'Nadi Group · read only · ticket #4182'], ['08:41', 'Rania Haddad · permission granted', 'Nadia · refund approval'], ['08:04', 'Support · feature flag changed', 'Arabic Coach app → Nadi Group'], ['Yesterday', 'Ziad Masri · refund approved', 'JOD 28.00 · Khalda'], ['Yesterday', 'Support · export', 'Tenant list · reason logged']];
    return dPage([
      h1('Audit log', 'All tenants · last 48 hours'),
      card(a.map(function (x, i) {
        return D({ key: i, display: 'flex', gap: 12, padding: '12px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', flexWrap: 'wrap', background: /impersonation/.test(x[1]) ? '#f4ece5' : 'transparent' }, [
          D({ font: '400 11px/1.5 ' + mono, color: C.t2, width: 64, flexShrink: 0 }, x[0]),
          D({ flex: 1, minWidth: 180 }, [D({ font: '450 12.5px/1.45 ' + sans }, x[1]), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, x[2])])
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Immutable. Impersonation entries are highlighted and visible to the tenant in their own audit log.')
    ]);
  };

  S['CON-13'] = function (v) {
    var b = [['Nadi Group', 'JOD 2,400.00', 'Paid 1 Aug', null], ['Fit Republic', 'JOD 9,800.00', 'Paid 1 Aug', null], ['Studio Nine', 'JOD 280.00', 'FAILED · retry 2 of 3', C.err], ['Iron House Riyadh', 'SAR 4,100.00', 'Paid 1 Aug', null]];
    return dPage([
      h1('Tenant billing', 'August · 1 failure'),
      card(b.map(function (x, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '450 13.5px/1.4 ' + sans, flex: 1 }, x[0]),
          D({ font: '500 12.5px/1.2 ' + mono }, x[1]),
          D({ font: '400 11px/1.4 ' + mono, color: x[3] || C.t2, width: 120, textAlign: 'end' }, x[2])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '15px 16px', borderColor: C.err }, [
        eyebrow('BEFORE YOU SUSPEND STUDIO NINE', C.err),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Suspending stops check-in for 214 members and locks their staff out of the app. Their card expired — a message usually fixes it faster than a suspension.'),
        D({ display: 'flex', gap: 9, marginTop: 12, flexWrap: 'wrap' }, [prim('Message them', function () { v.act('flash', 'Sent'); }), sec('Suspend · needs approval', function () {})])
      ]), { marginTop: 12 })
    ]);
  };

  S['CON-16'] = function (v) {
    return dPage([
      D({ maxWidth: 380, margin: '40px auto 0' }, [
        D({ width: 26, height: 26, borderRadius: 5, background: C.t1, color: C.surf, font: '500 14px/26px ' + sans, textAlign: 'center' }, 'V'),
        D({ font: '500 24px/1.18 ' + sans, letterSpacing: '-.018em', marginTop: 18 }, 'Veyro Console'),
        D({ font: '400 13px/1.6 ' + sans, color: C.t2, marginTop: 5 }, 'Internal. Staff sign-in only.'),
        D({ marginTop: 20 }, prim('Continue with Veyro SSO', function () { v.act('flash', 'SSO · MFA required'); v.openScreen('CON-01'); }, true)),
        D({ font: '400 12px/1.65 ' + sans, color: C.t2, marginTop: 14 }, 'There is no password option. Two-factor is required and cannot be turned off — this console can reach customer data.')
      ])
    ]);
  };

  S['CON-17'] = function (v) {
    return dPage([
      h1('Ticket #4182', 'Nadi Group · Rania Haddad · 2 hours ago'),
      card(D({ padding: '16px 17px' }, [
        D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26' }, '"The Khalda class roster is showing the wrong coach for Thursday spin. It says Omar but he declined it."'),
        D({ font: '400 12.5px/1.6 ' + sans, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, 'Reported from Admin → Scheduling → 19:00 Thursday')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT WE CAN SEE WITHOUT OPENING THEIR DATA'),
        D({ font: '400 13px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Version 4.18.2 · current\nNo errors logged on that screen\nClass assignment changed twice yesterday\nNo open incidents')
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'The change history suggests a stale assignment rather than a bug. Try that before opening their records — impersonation is the last resort, not the first.')), { marginTop: 12 }),
      D({ display: 'flex', gap: 9, marginTop: 14, flexWrap: 'wrap' }, [
        sec('Reply to Rania', function () { v.act('flash', 'Reply sent'); }),
        sec('Open their data', function () { v.openScreen('CON-09'); })
      ])
    ]);
  };


  S['MBR-04'] = function (v) {
    return mPage([
      D({ font: '500 30px/1.14 ' + sans, letterSpacing: '-.02em', marginTop: 24 }, 'Welcome to Khalda,\nAhmad'),
      D({ font: '400 15px/1.65 ' + sans, color: '#3d3b36', marginTop: 12 }, "Three quick things and we'll get out of your way."),
      card(D({ padding: '16px 17px' }, [
        eyebrow('WHAT ARE YOU AFTER'),
        D({ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }, [
          Btn(function () {}, { font: '450 15px/1.35 ' + sans, border: '2px solid ' + C.ink, background: '#f7f9fc', borderRadius: 6, padding: '15px 16px', minHeight: 48, display: 'flex', alignItems: 'center' }, 'Lose weight'),
          Btn(function () {}, { font: '450 15px/1.35 ' + sans, border: '1px solid ' + C.line, borderRadius: 6, padding: '15px 16px', minHeight: 48, display: 'flex', alignItems: 'center' }, 'Get stronger'),
          Btn(function () {}, { font: '450 15px/1.35 ' + sans, border: '1px solid ' + C.line, borderRadius: 6, padding: '15px 16px', minHeight: 48, display: 'flex', alignItems: 'center' }, 'Just stay active')
        ])
      ]), { marginTop: 20 }),
      D({ marginTop: 16 }, prim('Next', function () { v.openScreen('MBR-01'); }, true)),
      D({ marginTop: 9 }, Btn(function () { v.openScreen('MBR-01'); }, { font: '450 13.5px/1 ' + sans, color: C.t2, minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'center' }, 'Skip for now'))
    ]);
  };

  S['MBR-05'] = function (v) {
    return mPage([
      D({ width: 26, height: 26, borderRadius: 5, background: C.t1, color: C.surf, font: '500 14px/26px ' + sans, textAlign: 'center', marginTop: 30 }, 'V'),
      D({ font: '500 26px/1.18 ' + sans, letterSpacing: '-.018em', marginTop: 18 }, 'Sign in'),
      D({ font: '400 14px/1.65 ' + sans, color: '#3d3b36', marginTop: 8 }, "We'll text you a code — no password to remember."),
      D({ marginTop: 20 }, field('Phone number', '079 555 0134')),
      D({ marginTop: 16 }, prim('Send me a code', function () { v.act('flash', 'Code sent to 079 555 0134'); v.openScreen('MBR-01'); }, true)),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 14 }, "Use the number your club has on file and we'll find your membership automatically.")
    ]);
  };

  S['MBR-06'] = function (v) {
    return mPage([
      h1('Lower body', 'With Yousef · 09:45 · about 45 minutes'),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26' }, "Yousef swapped your squats for box squats — easier on your knee. Start lighter than last time.")), { marginTop: 14 }),
      card([['Box squat', '4 × 6 · from 55kg'], ['Romanian deadlift', '3 × 8 · from 90kg'], ['Leg press', '3 × 10 · from 160kg'], ['Walking lunge', '3 × 12 each'], ['Calf raise', '4 × 15 · from 40kg']].map(function (e, i) {
        return D({ key: i, display: 'flex', gap: 11, alignItems: 'center', padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '400 11px/1.4 ' + mono, color: C.t3, width: 16 }, String(i + 1)),
          D({ flex: 1 }, [D({ font: '450 15px/1.35 ' + sans }, e[0]), D({ font: '400 12px/1.5 ' + mono, color: C.t2, marginTop: 2 }, e[1])])
        ]);
      }), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Start', function () { v.openScreen('MBR-07'); }, true))
    ]);
  };

  S['MBR-09'] = function (v) {
    var h9 = [['Wednesday', 'Lower body', '41 min · 8 sets'], ['Monday', 'Upper body', '38 min · 9 sets'], ['Last Friday', 'Lower body', '44 min · 8 sets'], ['Last Wednesday', 'Upper body', '36 min · 9 sets']];
    return mPage([
      h1('What you have done', '32 sessions since March'),
      card(h9.map(function (r, i) {
        return Btn(function () { v.openScreen('MBR-08'); }, { display: 'flex', gap: 11, alignItems: 'center', padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ flex: 1 }, [D({ font: '450 14.5px/1.35 ' + sans }, r[1]), D({ font: '400 12px/1.5 ' + sans, color: C.t2, marginTop: 2 }, r[0])]),
          D({ font: '400 11.5px/1.4 ' + mono, color: C.t2 }, r[2])
        ]);
      }), { marginTop: 14 })
    ]);
  };

  S['MBR-11'] = function (v) {
    return mPage([
      h1('Chicken with rice', 'Lunch · 680 kcal'),
      card(D({ padding: '15px 16px' }, [
        eyebrow("WHAT'S IN IT"),
        D({ font: '400 14px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, '180g chicken breast\n150g rice, cooked\n120g lactose-free yoghurt\nSalad, olive oil'),
        D({ font: '400 12.5px/1.6 ' + mono, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, '52g protein · 74g carbs · 18g fat')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26' }, 'Yoghurt swapped for lactose-free automatically — Yousef knows about that.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Ate it', function () { v.act('meal', 'lunch'); v.openScreen('MBR-01'); }, true)),
      D({ marginTop: 9 }, sec('Show me something else', function () { v.openScreen('MBR-02'); }, true))
    ]);
  };

  S['MBR-12'] = function (v) {
    var f = [['Shawarma plate', 'Beef · 665 kcal', 'Yesterday'], ['Mansaf', 'Chicken · 720 kcal', 'Recent'], ['Labneh and bread', '340 kcal', 'Recent'], ['Falafel wrap', '480 kcal', 'Favourite']];
    return mPage([
      h1('What did you eat?', ''),
      D({ marginTop: 14, font: '400 15px/1.4 ' + sans, color: C.t3, border: '1px solid ' + C.line, borderRadius: 6, padding: '14px 15px', minHeight: 48, display: 'flex', alignItems: 'center' }, 'Search food'),
      D({ display: 'flex', gap: 8, marginTop: 12 }, [sec('Photo', function () { v.openScreen('MBR-14'); }, true), sec('Barcode', function () { v.openScreen('MBR-13'); }, true)]),
      card(f.map(function (r, i) {
        return Btn(function () { v.act('flash', r[0] + ' logged'); v.openScreen('MBR-01'); }, { display: 'flex', gap: 11, alignItems: 'center', padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ flex: 1 }, [D({ font: '450 14.5px/1.35 ' + sans }, r[0]), D({ font: '400 12px/1.5 ' + sans, color: C.t2, marginTop: 2 }, r[1])]),
          D({ font: '400 10.5px/1.4 ' + mono, color: C.t3 }, r[2])
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Portions are in plates and pieces, not grams. Nobody weighs a shawarma.')
    ]);
  };

  S['MBR-13'] = function (v) {
    return mPage([
      h1('Scan a barcode', ''),
      D({ marginTop: 16, height: 220, background: '#211f1c', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }, D({ width: 200, height: 90, border: '2px solid #7ea6e8', borderRadius: 4 })),
      card(D({ padding: '15px 16px' }, [
        D({ font: '500 15.5px/1.35 ' + sans }, 'Al Rabie orange juice 250ml'),
        D({ font: '400 12.5px/1.55 ' + mono, color: C.t2, marginTop: 4 }, '110 kcal · 0g protein · 26g carbs'),
        D({ marginTop: 12 }, prim('Log one bottle', function () { v.act('flash', 'Logged'); v.openScreen('MBR-01'); }, true))
      ]), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, "If we don't recognise something, you can add it by hand and the barcode gets attached for next time.")
    ]);
  };

  S['MBR-14'] = function (v) {
    return mPage([
      h1('Photograph your meal', ''),
      D({ marginTop: 16, height: 200, background: '#dcd7cf', borderRadius: 8 }),
      D({ border: '1px solid #4a3d7a', borderRadius: 6, marginTop: 14, overflow: 'hidden' }, [
        D({ padding: '9px 13px', background: '#edebf6', display: 'flex', gap: 7, alignItems: 'center' }, [
          D({ font: '400 10.5px/1 ' + mono, color: '#4a3d7a' }, '✦'),
          D({ font: '500 10px/1.4 ' + mono, color: '#4a3d7a', letterSpacing: '.06em' }, "OUR GUESS — CHECK IT'S RIGHT")
        ]),
        D({ padding: '13px 14px' }, [
          D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26' }, 'Grilled chicken, rice, salad. Roughly 640 kcal.'),
          D({ font: '400 12.5px/1.6 ' + sans, color: C.t2, marginTop: 8 }, "A guess from the photo, not a measurement. Adjust it if it looks wrong — Yousef sees what you log, not what we guessed.")
        ])
      ]),
      D({ marginTop: 16 }, prim('Looks right, log it', function () { v.act('flash', 'Logged · 640 kcal'); v.openScreen('MBR-01'); }, true)),
      D({ marginTop: 9 }, sec('Let me correct it', function () { v.openScreen('MBR-12'); }, true))
    ]);
  };

  S['MBR-15'] = function (v) {
    var g = [['Chicken breast', '1.2 kg'], ['Beef mince', '600 g'], ['Rice', '1 kg'], ['Lactose-free yoghurt', '4 pots'], ['Oats', '750 g'], ['Bananas', '7'], ['Dates', '400 g'], ['Flatbread', '10']];
    return mPage([
      h1('Your shopping', 'This week · 8 things'),
      card(g.map(function (r, i) {
        return Btn(function () { v.act('flash', r[0] + ' ticked off'); }, { display: 'flex', gap: 12, alignItems: 'center', padding: '13px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ font: '400 12px/1 ' + mono, color: C.ctl, width: 16 }, '☐'),
          D({ font: '450 14.5px/1.35 ' + sans, flex: 1 }, r[0]),
          D({ font: '400 12px/1.4 ' + mono, color: C.t2 }, r[1])
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, "Built from this week's meals. Anything you have already eaten drops off the list.")
    ]);
  };

  S['MBR-16'] = function (v) {
    return mPage([
      h1('Weekly check-in', 'Yousef sees this on Monday'),
      card(D({ padding: '16px 17px' }, [
        eyebrow('WEIGHT'),
        D({ font: '500 26px/1.15 ' + mono, marginTop: 8 }, '78.4 kg'),
        D({ font: '400 12.5px/1.6 ' + sans, color: C.t2, marginTop: 6 }, 'Down 0.6 kg from last week')
      ]), { marginTop: 14 }),
      card(D({ padding: '16px 17px' }, [
        eyebrow('HOW DID THE WEEK GO'),
        D({ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }, [
          Btn(function () {}, { font: '500 13px/1 ' + sans, background: C.t1, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Mostly stuck to it'),
          sec('Struggled', function () {}, true)
        ])
      ]), { marginTop: 12 }),
      card(D({ padding: '16px 17px' }, [
        eyebrow('ANYTHING HE SHOULD KNOW'),
        D({ font: '400 14px/1.6 ' + sans, color: C.t3, border: '1px solid ' + C.line, borderRadius: 6, padding: '13px 14px', marginTop: 8, minHeight: 66 }, 'Optional')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Send to Yousef', function () { v.act('flash', 'Sent — he usually replies Monday'); v.openScreen('MBR-01'); }, true))
    ]);
  };

  S['MBR-21'] = function (v) {
    var s = [['Wednesday', '09:45', true], ['Wednesday', '17:30', true], ['Friday', '09:45', true], ['Friday', '16:00', false]];
    return mPage([
      h1('Book with Yousef', '3 credits left'),
      card(s.map(function (r, i) {
        return Btn(function () { if (r[2]) { v.act('flash', 'Booked ' + r[0] + ' ' + r[1] + ' · 2 credits left'); v.openScreen('MBR-17'); } }, { display: 'flex', gap: 12, alignItems: 'center', padding: '14px 15px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 48, opacity: r[2] ? 1 : 0.5 }, [
          D({ flex: 1 }, [D({ font: '450 14.5px/1.35 ' + sans }, r[0]), D({ font: '400 13px/1.5 ' + mono, color: C.t2, marginTop: 2 }, r[1])]),
          D({ font: '400 11px/1.4 ' + mono, color: r[2] ? C.ok : C.t3 }, r[2] ? 'FREE' : 'TAKEN')
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26' }, 'Booking uses one of your three remaining credits. They run out in November.')), { marginTop: 12 })
    ]);
  };

  S['MBR-28'] = function (v) {
    var w = [['Class credit · Yoga cancelled', '+JOD 12.50', '14 Aug'], ['Spent on water', '−JOD 0.50', '12 Aug'], ['Top-up', '+JOD 20.00', '1 Aug']];
    return mPage([
      h1('Your balance', ''),
      card(D({ padding: '17px 18px' }, [
        D({ font: '500 30px/1.15 ' + mono }, 'JOD 12.50'),
        D({ font: '400 12.5px/1.6 ' + sans, color: C.t2, marginTop: 7 }, 'Use it at the desk or for classes. The 12.50 from the cancelled yoga class expires 14 November.')
      ]), { marginTop: 14 }),
      card(w.map(function (r, i) {
        return D({ key: i, display: 'flex', gap: 11, alignItems: 'center', padding: '13px 15px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ flex: 1 }, [D({ font: '450 13.5px/1.35 ' + sans }, r[0]), D({ font: '400 11px/1.4 ' + mono, color: C.t2, marginTop: 2 }, r[2])]),
          D({ font: '500 13px/1.2 ' + mono, color: r[1][0] === '+' ? C.ok : C.t1 }, r[1])
        ]);
      }), { marginTop: 12 }),
      D({ marginTop: 14 }, sec('Add money', function () { v.act('flash', 'Top-up'); }, true))
    ]);
  };

  S['MBR-30'] = function (v) {
    var m = [['them', 'How is the knee feeling after Wednesday?', '1d'], ['me', 'Better actually. The box squats helped', '1d'], ['them', 'Good. Keep it at 55 this week and we will see', '20h']];
    return mPage([
      h1('Yousef Haddad', 'Usually replies within a day'),
      D({ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 16 }, m.map(function (x, i) {
        var mine = x[0] === 'me';
        return D({ key: i, alignSelf: mine ? 'flex-end' : 'flex-start', maxWidth: '80%', background: mine ? C.wash : C.canvas, borderRadius: mine ? '8px 8px 2px 8px' : '8px 8px 8px 2px', padding: '12px 14px' }, [
          D({ font: '400 13.5px/1.62 ' + sans }, x[1]),
          D({ font: '400 10px/1.4 ' + mono, color: C.t2, marginTop: 4 }, x[2])
        ]);
      })),
      D({ marginTop: 16, display: 'flex', gap: 9, alignItems: 'center' }, [
        D({ flex: 1, font: '400 13.5px/1.5 ' + sans, color: C.t3, border: '1px solid ' + C.line, borderRadius: 6, padding: '13px 14px', minHeight: 48, display: 'flex', alignItems: 'center' }, 'Message Yousef'),
        prim('Send', function () { v.act('flash', 'Sent'); })
      ])
    ]);
  };

  S['MBR-38'] = function (v) {
    return mPage([
      D({ display: 'flex', gap: 11, padding: '14px 15px', background: '#f4ece5', border: '1px solid rgba(138,90,31,.4)', borderRadius: 6, alignItems: 'flex-start', marginTop: 6 }, [
        D({ width: 3, alignSelf: 'stretch', background: C.warn, flexShrink: 0 }),
        D({ flex: 1 }, [
          D({ font: '500 14.5px/1.35 ' + sans }, 'No signal down here'),
          D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26', marginTop: 4 }, "Your workout and your plan are on your phone already. Anything you log will send itself when you're back in range.")
        ])
      ]),
      D({ font: '400 13px/1.5 ' + sans, color: C.t2, marginTop: 20 }, 'Wednesday morning'),
      D({ font: '500 30px/1.12 ' + sans, letterSpacing: '-.02em', marginTop: 2 }, 'Lower body\nat 09:45'),
      D({ marginTop: 18 }, prim('Start the session', function () { v.openScreen('MBR-07'); }, true)),
      card(D({ padding: '15px 16px' }, [
        eyebrow("WHAT WON'T WORK RIGHT NOW", C.warn),
        D({ font: '400 13.5px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Booking a class\nPaying anything\nMessaging Yousef'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9 }, 'Your entry pass still works — it does not need a signal.')
      ]), { marginTop: 20 })
    ]);
  };

  S['CCH-08'] = function (v) {
    return mPage([
      h1('Lower-body strength', '12 weeks · 3 days · for Ahmad'),
      D({ border: '1px solid #4a3d7a', borderRadius: 6, marginTop: 14, overflow: 'hidden' }, [
        D({ padding: '8px 13px', background: '#edebf6', display: 'flex', gap: 7, alignItems: 'center' }, [
          D({ font: '400 10.5px/1 ' + mono, color: '#4a3d7a' }, '✦'),
          D({ font: '500 10px/1.4 ' + mono, color: '#4a3d7a', letterSpacing: '.06em' }, 'STARTED FROM A TEMPLATE, ADJUSTED FOR HIM')
        ]),
        D({ padding: '11px 13px', font: '400 12.5px/1.7 ' + sans, color: '#2c2a26' }, 'Deep squats replaced with box squats — his intake records a 2019 meniscus repair with no deep loaded flexion.')
      ]),
      D({ display: 'flex', gap: 6, marginTop: 14, flexWrap: 'wrap' }, [
        Btn(function () {}, { font: '500 11.5px/1 ' + sans, background: C.t1, color: C.surf, padding: '10px 12px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Wk 1–4'),
        sec('5–8', function () {}), sec('9–12', function () {})
      ]),
      card([['Box squat', '4 × 6 · from 60kg', 'SUBSTITUTED'], ['Romanian deadlift', '3 × 8 · from 90kg', ''], ['Leg press', '3 × 10 · from 160kg', ''], ['Walking lunge', '3 × 12 each', ''], ['Calf raise', '4 × 15 · from 40kg', '']].map(function (e, i) {
        return D({ key: i, display: 'flex', gap: 10, alignItems: 'center', padding: '13px 14px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '400 11px/1.4 ' + mono, color: C.t3, width: 14 }, '⣿'),
          D({ flex: 1, minWidth: 0 }, [D({ font: '450 14px/1.4 ' + sans }, e[0]), D({ font: '400 11.5px/1.5 ' + mono, color: C.t2, marginTop: 2 }, e[1])]),
          e[2] ? badge(e[2], C.warn) : null
        ]);
      }).concat([Btn(function () { v.openScreen('CCH-09'); }, { padding: '13px 14px', borderTop: '1px solid ' + C.hair, font: '500 13px/1.4 ' + sans, color: C.ink, minHeight: 44, display: 'flex', alignItems: 'center' }, '＋ Add exercise')]), { marginTop: 12 }),
      card(D({ padding: '13px 14px', background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'Progression: +2.5kg on the main lift each week if all sets complete. Applied to weeks 5–12 automatically.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Assign to Ahmad', function () { v.openScreen('CCH-10'); }, true))
    ]);
  };

  S['CCH-10'] = function (v) {
    return mPage([
      h1('Assign the programme', 'Lower-body strength · 12 weeks'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('TO WHOM'),
        D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Ahmad Nabulsi'),
        D({ font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.07em', marginTop: 12 }, 'WHICH DAYS'),
        D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Monday, Wednesday, Friday')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('TELL HIM'),
        D({ display: 'flex', gap: 8, marginTop: 9, flexWrap: 'wrap' }, [
          Btn(function () {}, { font: '500 12.5px/1 ' + sans, background: C.t1, color: C.surf, padding: '13px 14px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Now'),
          sec('On Monday morning', function () {}, true)
        ])
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Assign it', function () { v.act('flash', 'Assigned · Ahmad notified'); v.openScreen('CCH-05'); }, true))
    ]);
  };

  S['CCH-12'] = function (v) {
    return mPage([
      h1('New client', 'Intake · Rana Sabbagh'),
      card(D({ padding: '16px 17px' }, [
        eyebrow('WHAT SHE WANTS'),
        D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Lose weight · 3 days a week · prefers classes')
      ]), { marginTop: 14 }),
      card(D({ padding: '16px 17px' }, [
        eyebrow('ANYTHING TO WORK AROUND', C.warn),
        D({ font: '400 14px/1.6 ' + sans, color: C.t3, border: '1px solid ' + C.line, borderRadius: 6, padding: '13px 14px', marginTop: 8, minHeight: 66 }, 'Injuries, conditions, medication…'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9 }, "Whatever you record here flags in the programme builder when it conflicts. It warns, it doesn't block — you decide.")
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Anything clinical needs someone qualified for that in your market. Veyro does not decide what counts as clinical.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Save and build her programme', function () { v.openScreen('CCH-08'); }, true))
    ]);
  };

  S['CCH-13'] = function (v) {
    return mPage([
      h1('Ahmad · nutrition', 'Day 1 of 7 · 2,150 kcal'),
      card([['BREAKFAST', 'Oats, banana, whey', '520'], ['LUNCH', 'Chicken with rice', '680'], ['AFTER TRAINING', 'Whey and dates', '310'], ['DINNER', 'Beef kofta, salad', '640']].map(function (m, i) {
        return D({ key: i, padding: '13px 14px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ display: 'flex', gap: 8, alignItems: 'baseline' }, [
            D({ font: '400 10px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em', flex: 1 }, m[0]),
            D({ font: '500 11.5px/1.2 ' + mono, color: C.t2 }, m[2] + ' kcal')
          ]),
          D({ font: '450 14px/1.4 ' + sans, marginTop: 4 }, m[1]),
          D({ display: 'flex', gap: 8, marginTop: 9 }, [sec('Swap', function () { v.act('flash', 'Alternatives'); }), sec('Adjust', function () { v.act('flash', 'Portion editor'); })])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '13px 14px', background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'Copy this day across the week, or leave the other six as generated.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Send the changes to Ahmad', function () { v.act('flash', 'Updated · he sees what changed'); }, true))
    ]);
  };

  S['CCH-14'] = function (v) {
    return mPage([
      h1("Ahmad's week", 'Check-in received Monday'),
      D({ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('WEIGHT', '78.4 kg', 'down 0.6'),
        metric('STUCK TO IT', '5 of 7', 'days on plan')
      ]),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT HE SAID'),
        D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, '"Weekend was hard, ate out twice. Weekdays were fine."')
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHAT HE ACTUALLY LOGGED'),
        D({ font: '400 13px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Protein averaged 148g against a 165g target\nTwo shawarma plates on Friday and Saturday\nWeekday meals matched the plan')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Adjust his targets', function () { v.openScreen('CCH-13'); }, true)),
      D({ marginTop: 9 }, sec('Message him', function () { v.openScreen('CCH-15'); }, true))
    ]);
  };

  S['CCH-19'] = function (v) {
    return mPage([
      D({ width: 26, height: 26, borderRadius: 5, background: C.t1, color: C.surf, font: '500 14px/26px ' + sans, textAlign: 'center', marginTop: 30 }, 'V'),
      D({ font: '500 26px/1.18 ' + sans, letterSpacing: '-.018em', marginTop: 18 }, 'Veyro Coach'),
      D({ font: '400 14px/1.65 ' + sans, color: '#3d3b36', marginTop: 8 }, 'Khalda'),
      D({ marginTop: 20 }, field('Email', 'yousef@nadigroup.jo')),
      D({ marginTop: 16 }, prim('Sign in', function () { v.openScreen('CCH-01'); }, true)),
      card(D({ padding: '15px 16px', background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'On a shared gym iPad, face unlock is off and you are signed out after fifteen minutes — client health details are on this device.')), { marginTop: 20 })
    ]);
  };


  S['ADM-CC-02'] = function (v) {
    return dPage([
      h1('Khalda · two things before the 09:00 rush', 'Wednesday 19 August · your club · data through 08:38'),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 16 }, [
        metric('IN THE BUILDING', '61', 'capacity 180'),
        metric('CLASSES TODAY', '11', '1 without a coach'),
        metric('STAFF ON SHIFT', '7 of 8', 'Yousef in at 10:00'),
        metric('EXPIRING · 7 DAYS', '6', '2 need a call')
      ]),
      card([
        attnRow(v, 'COACHING', C.err, '31 PT sessions delivered but not verified', 'Omar has 22, Yousef 9. Unverified sessions are not billed and do not count against a package — members may think they have credits they have used.', 'Ask both coaches to verify', 'CCH-17'),
        attnRow(v, 'STAFFING', C.warn, 'Spin has no coach and 18 members booked', 'Omar declined. Dana and Yousef are both qualified and free at 19:00 tomorrow.', 'Offer to Dana', 'ADM-SCH-02'),
        condRow(v, 'MONEY', C.info, '2 of this morning\u2019s failed payments are your members — Nadia is handling recovery', 'ADM-PAY-05')
      ], { marginTop: 16 }),
      card(D({ padding: '13px 15px' }, D({ font: '400 12px/1.65 ' + sans, color: '#3d3b36' }, 'What Ziad does not see: group revenue, cross-location comparison, the JoFotara queue, or the recovery workflow itself. Enough to answer a question at the desk, without financial administration he cannot act on.')), { marginTop: 14 })
    ]);
  };

  S['ADM-CC-03'] = function (v) {
    return dPage([
      D({ display: 'flex', gap: 11, padding: '13px 16px', background: '#f4ece5', border: '1px solid rgba(138,59,31,.3)', borderRadius: 4, alignItems: 'flex-start' }, [
        D({ width: 3, alignSelf: 'stretch', background: C.err, flexShrink: 0 }),
        D({ flex: 1 }, [
          D({ font: '500 15px/1.35 ' + sans }, 'The turnstiles at Sweifieh are not reading cards'),
          D({ font: '400 13px/1.68 ' + sans, color: '#2c2a26', marginTop: 4 }, 'The access controller stopped responding at 09:04. Members cannot enter with a card or the app. Check-in at the desk still works and every entry is recorded, so nothing is lost. Bookings, payments and classes are unaffected.'),
          D({ display: 'flex', gap: 9, marginTop: 11, flexWrap: 'wrap' }, [
            prim('Open manual check-in', function () { v.openScreen('FD-01'); }),
            sec('Notify Sweifieh staff', function () { v.act('flash', 'Staff notified'); }),
            sec('Hardware status', function () { v.openScreen('FD-08'); })
          ]),
          D({ font: '400 10.5px/1.5 ' + mono, color: C.t2, marginTop: 9 }, 'Retrying every 30s · 16 minutes elapsed · stays visible until the controller responds')
        ])
      ]),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 16 }, [
        metric('ENTRIES SINCE 09:04', '23', 'all recorded at the desk'),
        metric('IN THE BUILDING', '48', 'capacity 140'),
        metric('CLASSES TODAY', '9', 'running normally'),
        metric('COLLECTED TODAY', 'JOD 486.00', 'unaffected')
      ]),
      card(D({ padding: '13px 15px' }, D({ font: '400 12px/1.65 ' + sans, color: '#3d3b36' }, 'Why the metrics stay neutral: 48 people in the building is a fact, not a problem. Colouring it red during an unrelated outage teaches staff to distrust the colour.')), { marginTop: 14 })
    ]);
  };

  S['ADM-CC-04'] = function (v) {
    return dPage([
      D({ font: '500 26px/1.18 ' + sans, letterSpacing: '-.018em' }, 'Nothing needs you at Abdoun'),
      D({ font: '400 13.5px/1.6 ' + sans, color: '#3d3b36', marginTop: 6 }, 'Payments, access, bookings and staffing are all clear. Last checked 14:20.'),
      D({ display: 'flex', gap: 26, marginTop: 20, paddingTop: 16, borderTop: '1px solid ' + C.line, flexWrap: 'wrap' }, [
        stat('312', 'VISITS TODAY'), stat('JOD 2,140.00', 'COLLECTED'), stat('9', 'NEW LEADS'), stat('96%', 'CLASS FILL')
      ]),
      D({ display: 'flex', gap: 9, marginTop: 18, flexWrap: 'wrap' }, [
        sec("Review this week's renewals", function () { v.openScreen('ADM-MEM-05'); }),
        sec('7 resolved today', function () { v.openScreen('ADM-CC-07'); })
      ]),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 16, maxWidth: '68ch' }, 'No illustration and no "all caught up!" — it reports the day and offers the next useful thing. A manager seeing this should feel informed, not congratulated.')
    ]);
  };

  S['ADM-CC-05'] = function (v) {
    return dPage([
      D({ display: 'flex', gap: 10, padding: '12px 14px', border: '1px solid ' + C.warn, borderRadius: 4, alignItems: 'flex-start' }, [
        D({ width: 3, alignSelf: 'stretch', background: C.warn, flexShrink: 0 }),
        D({ flex: 1 }, [
          D({ font: '500 14px/1.35 ' + sans }, 'Revenue analytics are 40 minutes behind'),
          D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26', marginTop: 3 }, 'The reporting pipeline is catching up after overnight maintenance. Figures shown are correct as of 08:00 — they are not wrong, only late. Attention items, member records and payments are live.'),
          D({ font: '400 10.5px/1.5 ' + mono, color: C.t2, marginTop: 7 }, 'Next attempt in 4 minutes')
        ])
      ]),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 16 }, [
        staleMetric('COLLECTED · MTD', 'JOD 41,280.00', 'as of 08:00', true),
        staleMetric('ACTIVE MEMBERS', '4,812', 'live', false),
        staleMetric('VISITS TODAY', '218', 'live', false),
        staleMetric('LEAD CONVERSION', '31%', 'as of 08:00', true)
      ]),
      card([
        D({ padding: '9px 14px', background: C.sunk, font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'AI PANEL · WITHHELD'),
        D({ padding: '12px 14px', font: '400 12.5px/1.65 ' + sans, color: '#3d3b36' }, 'Veyro is not offering a revenue interpretation while the underlying figures are stale. It will return when the pipeline catches up.')
      ], { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 14, maxWidth: '72ch' }, 'Per-panel provenance, not a page-level spinner. Stale numbers de-emphasise and carry a timestamp; live ones stay primary. An interpretation built on stale inputs is worse than no interpretation.')
    ]);
  };

  S['ADM-CRM-02'] = function (v) {
    var rows = [['Rana Sabbagh', 'Sweifieh open day', '2 days', 'No contact', C.warn], ['Omar Zaid', 'Instagram', '4 hours', 'New', null], ['Lina Haddad', 'Referral · Dana', '1 day', 'Called', null], ['Faris Alami', 'Walk-in', '3 days', 'Toured', null], ['Yara Nimri', 'Google', '6 days', 'On trial · day 6', C.warn], ['Tareq Fayez', 'Instagram', '8 days', 'No contact', C.err]];
    return dPage([
      h1('Leads', '36 open · 7 going cold · Khalda'),
      filterBar(['No contact 48h', 'Trial ending', 'All 36']),
      table(['LEAD', 'SOURCE', 'AGE', 'STAGE'], rows.map(function (r) {
        return [r[0], r[1], r[2], { t: r[3], c: r[4] }];
      }), function () { v.openScreen('ADM-CRM-03'); }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Sales sees their own leads by default. Ziad sees the whole club. Nobody sees another club unless their role spans it.')
    ]);
  };

  S['ADM-CRM-03'] = function (v) {
    return dPage([
      D({ display: 'flex', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }, [
        D({ width: 44, height: 44, borderRadius: '50%', background: '#dcd7cf', flexShrink: 0 }),
        D({ flex: 1, minWidth: 220 }, [
          D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [
            D({ font: '500 21px/1.2 ' + sans, letterSpacing: '-.015em' }, 'Rana Sabbagh'),
            badge('NO CONTACT · 2 DAYS', C.warn)
          ]),
          D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 4 }, 'Sweifieh open day · 079 411 0288 · interested in classes and PT')
        ]),
        D({ display: 'flex', gap: 8, flexWrap: 'wrap' }, [prim('Start a 7-day trial', function () { v.openScreen('ADM-CRM-05'); }), sec('WhatsApp', function () { v.openScreen('ADM-COM-01'); })])
      ]),
      card([
        tl('2 days ago', 'Registered at the Sweifieh open day', 'Asked about the 19:00 spin class twice'),
        tl('2 days ago', 'Added to Layla\u2019s list', 'Automatic · open-day source'),
        tl('Yesterday', 'Automated welcome message sent', 'Delivered, not opened')
      ], { marginTop: 16 }),
      aiPanel('Offer the trial with a spin booking already held', 'She asked about the 19:00 spin class twice at the open day and mentioned she works in Abdoun. Four of the eleven who joined this month came in through a class, not a tour.', v)
    ]);
  };

  S['ADM-CRM-04'] = function (v) {
    return dPage([
      h1('Add a lead', 'Khalda'),
      card(D({ padding: '16px 18px', maxWidth: 520 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Name', 'Rana Sabbagh'), field('Phone', '079 411 0288'), field('Where from', 'Sweifieh open day'), field('Interested in', 'Classes, personal training')
      ])), { marginTop: 14 }),
      card(D({ padding: '13px 15px', background: C.sunk, maxWidth: 520 }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'Name and phone is enough. A lead captured badly beats a lead not captured — the rest can be filled in later.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Add her', function () { v.act('flash', 'Added · assigned to Layla'); v.openScreen('ADM-CRM-03'); }, true))
    ]);
  };

  S['ADM-CRM-07'] = function (v) {
    return dPage([
      h1('Mark Tareq Fayez as lost', 'Instagram · 8 days · never contacted'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, [
        eyebrow('WHY'),
        D({ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }, ['Too expensive', 'Joined somewhere else', 'Never replied', 'Wrong number', 'Not ready yet'].map(function (r, i) {
          return Btn(function () {}, { font: '450 14px/1.35 ' + sans, border: i === 2 ? '2px solid ' + C.ink : '1px solid ' + C.line, background: i === 2 ? '#f7f9fc' : 'transparent', borderRadius: 6, padding: '13px 14px', minHeight: 44, display: 'flex', alignItems: 'center' }, r);
        }))
      ]), { marginTop: 14 }),
      card(D({ padding: '13px 15px', background: C.sunk, maxWidth: 560 }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'This feeds the source report — eight days without contact is what lost him, and Instagram leads going cold is a pattern worth seeing. He can be reopened after 90 days.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Mark as lost', function () { v.act('flash', 'Marked lost · never replied'); v.openScreen('ADM-CRM-02'); }, true))
    ]);
  };


  S['ADM-MEM-02'] = function (v) {
    return dPage([
      memberHeader(v, 'Dana Qasem', 'Club+ · Khalda · since Jan 2023 · M-02914', null, null),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 16 }, [
        metric('BALANCE', 'JOD 0.00', ''), metric('RENEWS', '24 Sep', 'automatically'),
        metric('VISITS · 30D', '18', 'three a week'), metric('WALLET', 'JOD 12.50', 'expires Nov')
      ]),
      card([
        tl('09:04 today', 'Checked in · Khalda', 'Card at the turnstile'),
        tl('09:00 today', 'PT with Yousef · verified', '4th of 10'),
        tl('24 Aug', 'Membership renewed · Club+', 'JOD 78.00 · Visa ···2201')
      ], { marginTop: 16 }),
      card(D({ padding: '13px 15px' }, D({ font: '400 12px/1.65 ' + sans, color: '#3d3b36' }, 'No green badges. Paid, active and granted are the expected cases — decorating them makes a genuinely overdue row harder to spot. The absence of an alert band is the signal.')), { marginTop: 14 })
    ]);
  };

  S['ADM-MEM-03'] = function (v) {
    return dPage([
      memberHeader(v, 'Ahmad Nabulsi', 'Club · Khalda · 079 555 0134', 'OWES', C.warn),
      card(D({ display: 'flex' }, [
        D({ width: 3, background: C.warn, flexShrink: 0 }),
        D({ flex: 1, padding: '13px 15px' }, [
          D({ font: '500 14px/1.35 ' + sans }, 'He owes JOD 55.00 — mention it, don\u2019t block him'),
          D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 3 }, 'His card expired. He can train until 2 September. Offer to take payment at the desk or send him a link.'),
          D({ display: 'flex', gap: 8, marginTop: 10 }, [prim('Take payment', function () { v.openScreen('ADM-PAY-04'); }), sec('Send link', function () { v.act('flash', 'Link sent'); })])
        ])
      ]), { marginTop: 16, borderColor: C.warn }),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('OUTSTANDING', 'JOD 55.00', ''), metric('ACCESS', 'Granted', 'grace to 2 Sep'),
        metric('MEMBERSHIP', '21 Aug', 'expires'), metric('NEXT BOOKING', 'None', '')
      ]),
      card([
        D({ padding: '9px 15px', background: C.sunk, font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'VISITS AND PAYMENTS ONLY'),
        tl('06:12', 'Payment failed', 'JOD 55.00'),
        tl('31 Jul', 'Checked in · Khalda', '')
      ], { marginTop: 14 }),
      card(D({ padding: '13px 15px' }, D({ font: '400 12px/1.65 ' + sans, color: '#3d3b36' }, 'Absent, not greyed: no coaching panel, no health notes, no PT credits, no commitment terms, no refund action. Layla sees what she needs to greet him and take his money.')), { marginTop: 14 })
    ]);
  };

  S['ADM-MEM-04'] = function (v) {
    return dPage([
      memberHeader(v, 'Yara Mansour', 'Club+ · Abdoun · since Jun 2022', 'FROZEN', C.info),
      card(D({ display: 'flex' }, [
        D({ width: 3, background: C.info, flexShrink: 0 }),
        D({ flex: 1, padding: '13px 15px' }, [
          D({ font: '500 14px/1.35 ' + sans }, 'Frozen until 1 October · travel'),
          D({ font: '400 12.5px/1.62 ' + sans, color: '#3d3b36', marginTop: 3 }, 'Approved by Rania on 28 July. Billing is paused, access is off, and her Club+ rate is held. She has used 2 of 3 freeze months this year.'),
          D({ display: 'flex', gap: 8, marginTop: 10 }, [sec('Resume early', function () { v.openScreen('ADM-MSH-04'); }), sec('Extend · needs approval', function () { v.act('flash', 'Request sent to Rania'); })])
        ])
      ]), { marginTop: 16 }),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('BALANCE', 'JOD 0.00', ''), metric('BILLING', 'Paused', ''), metric('ACCESS', 'Off', 'by agreement'), metric('RESUMES', '1 Oct', '')
      ]),
      card(D({ padding: '13px 15px' }, D({ font: '400 12px/1.65 ' + sans, color: '#3d3b36' }, 'Frozen is info severity, not warning — a normal agreed arrangement, not a problem. Access reads "Off", never "Denied": denied means something went wrong, off means someone chose it.')), { marginTop: 14 })
    ]);
  };

  S['ADM-MEM-06'] = function (v) {
    return dPage([
      h1('Ahmad Nabulsi · billing', 'Club · JOD 55.00 monthly'),
      table(['INVOICE', 'PERIOD', 'AMOUNT', 'STATE'], [
        ['INV-20418', 'August', 'JOD 55.00', { t: 'UNPAID · 2 DAYS', c: C.err }],
        ['INV-20301', 'July', 'JOD 55.00', { t: 'PAID', c: C.t2 }],
        ['INV-20194', 'June', 'JOD 55.00', { t: 'PAID', c: C.t2 }],
        ['INV-19871', 'PT · 10 sessions', 'JOD 280.00', { t: 'PAID', c: C.t2 }]
      ], function () { v.openScreen('ADM-PAY-03'); }),
      card(D({ padding: '15px 16px', maxWidth: 560 }, [
        eyebrow('HOW HE PAYS'),
        D({ font: '400 13px/1.75 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Visa ···4417 · expired July 2026\nNo backup method'),
        D({ font: '400 12px/1.6 ' + sans, color: C.warn, marginTop: 8 }, 'No backup is why this failed three times rather than once.')
      ]), { marginTop: 14 })
    ]);
  };

  S['ADM-MEM-07'] = function (v) {
    return dPage([
      h1('Ahmad Nabulsi · attendance', '19 days since his last visit'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('LAST 12 WEEKS'),
        D({ display: 'flex', alignItems: 'flex-end', gap: 4, height: 64, marginTop: 12 }, [3,3,2,3,3,2,3,3,1,0,0,0].map(function (n, i) {
          return D({ key: i, flex: 1, height: (n / 3 * 100 || 4) + '%', background: n === 0 ? '#ece9e3' : i > 7 ? C.warn : '#cbc6bc', borderRadius: 1 });
        })),
        D({ font: '400 12.5px/1.6 ' + sans, color: '#2c2a26', marginTop: 10 }, 'Three a week for eight weeks, then nothing for three. No message, no cancellation — he just stopped.')
      ]), { marginTop: 14 }),
      card([tl('31 Jul 18:40', 'Checked in · Khalda', 'Card · last visit'), tl('29 Jul 18:32', 'Checked in · Khalda', 'Card'), tl('27 Jul 09:10', 'Checked in · Khalda', 'App pass')], { marginTop: 12 })
    ]);
  };

  S['ADM-MEM-08'] = function (v) {
    var docs = [['Membership agreement', 'Signed 4 Mar 2024', 'v3', null], ['Health questionnaire', 'Completed 4 Mar 2024', '', null], ['Photo ID', 'Uploaded 4 Mar 2024', '', null], ['Medical clearance', 'Expires 12 Sep 2026', '', C.warn]];
    return dPage([
      h1('Ahmad Nabulsi · documents', 'One expiring'),
      card(docs.map(function (d2, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '14px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ flex: 1 }, [D({ font: '450 13.5px/1.4 ' + sans }, d2[0]), D({ font: '400 11.5px/1.5 ' + sans, color: d2[3] || C.t2, marginTop: 2 }, d2[1])]),
          d2[2] ? D({ font: '400 10.5px/1.4 ' + mono, color: C.t2 }, d2[2]) : null,
          sec('View', function () { v.act('flash', 'Opening ' + d2[0]); })
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '13px 15px', background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'The medical clearance expiry raises a Command Center item three weeks out. Medical documents are visible only to roles with health permission — Layla sees the row exists, not the file.')), { marginTop: 12 })
    ]);
  };

  S['ADM-MEM-09'] = function (v) {
    return dPage([
      h1('Ahmad Nabulsi · notes and messages', ''),
      card([
        D({ padding: '13px 15px', background: C.sunk, font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'STAFF NOTES · NEVER VISIBLE TO THE MEMBER'),
        noteRow('Ziad Masri', '2 days ago', 'Called about the failed payment, no answer. Will try again Thursday.'),
        noteRow('Layla Odeh', '3 weeks ago', 'Asked whether he could freeze rather than cancel. Explained the options.')
      ], { marginTop: 14 }),
      card(D({ padding: '13px 15px' }, [
        eyebrow('CONSENT'),
        D({ font: '400 12.5px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Marketing withdrawn 12 July. Service messages about payments, bookings and access are still permitted.')
      ]), { marginTop: 12 }),
      D({ marginTop: 14 }, sec('Open the WhatsApp thread', function () { v.openScreen('ADM-COM-01'); }, true))
    ]);
  };

  S['ADM-MEM-10'] = function (v) {
    return dPage([
      h1('Add a member', 'Walk-in · Khalda'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Name', 'Sara Halabi'), field('Phone', '079 555 0134'), field('Email', 'sara.halabi@gmail.com'), field('Date of birth', '14 / 03 / 1994'), field('Emergency contact', 'Rami Halabi · 079 555 0199')
      ])), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 560, borderColor: C.info }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'No existing record matches 079 555 0134. If one did, we would offer it rather than creating a second Sara Halabi.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Add her, then sell a membership', function () { v.openScreen('ADM-MSH-01'); }, true))
    ]);
  };

  S['ADM-MEM-11'] = function (v) {
    return dPage([
      h1('Merge two records', 'Ahmad Nabulsi · possible duplicate'),
      card(D({ padding: '0', maxWidth: 700 }, [
        D({ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 12, padding: '10px 16px', background: C.sunk, borderBottom: '1px solid ' + C.line }, [
          D({ font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'FIELD'),
          D({ font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'M-04188 · KEEP'),
          D({ font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'M-04901 · MERGE IN')
        ]),
        mergeRow('Phone', '079 555 0134', '079 555 0134'),
        mergeRow('Joined', '4 Mar 2024', '11 Aug 2026'),
        mergeRow('Plan', 'Club · active', 'Flex · never paid'),
        mergeRow('Payments', '17 invoices', '0 invoices'),
        mergeRow('Visits', '214', '1')
      ]), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 700, borderColor: C.err }, [
        eyebrow('THIS CANNOT BE UNDONE', C.err),
        D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Payment history from both always merges. Type the surviving member ID to confirm.'),
        D({ marginTop: 11 }, field('Confirm the ID you are keeping', 'M-04188'))
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, D({ display: 'flex', gap: 9, flexWrap: 'wrap' }, [
        Btn(function () { v.act('flash', 'Merged into M-04188'); v.openScreen('ADM-MEM-01'); }, { font: '500 13px/1 ' + sans, background: C.err, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Merge them'),
        sec('Cancel', function () { v.openScreen('ADM-MEM-05'); }, true)
      ]))
    ]);
  };

  S['ADM-MSH-02'] = function (v) {
    return dPage([
      h1('Renew Ahmad Nabulsi', 'Club · expires 21 August'),
      card(D({ padding: '15px 17px', maxWidth: 560, borderColor: C.warn }, [
        eyebrow('THE PRICE HAS CHANGED SINCE HE LAST RENEWED', C.warn),
        D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'He has been paying JOD 55.00. Club is now JOD 58.00. You must tell him before this goes through.')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560, background: C.sunk }, [
        row('From 21 August', 'JOD 58.00'), row('He pays now', 'JOD 55.00'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9, paddingTop: 9, borderTop: '1px solid ' + C.hair }, 'Or hold his old price for another twelve months if you would rather not lose him this week.')
      ]), { marginTop: 12 }),
      D({ display: 'flex', gap: 9, marginTop: 16, flexWrap: 'wrap' }, [
        prim('Renew at JOD 58.00', function () { v.act('flash', 'Renewed · he was told'); }, true),
        sec('Hold his old price', function () { v.act('flash', 'Renewed at JOD 55.00 · noted'); }, true)
      ])
    ]);
  };

  S['ADM-MSH-04'] = function (v) {
    return dPage([
      h1('Bring Yara back early', 'Frozen until 1 October'),
      card(D({ padding: '15px 17px', maxWidth: 520 }, [
        field('Restart on', '1 September 2026'),
        D({ marginTop: 13, paddingTop: 13, borderTop: '1px solid ' + C.hair }, [
          row('Part month, 1–30 Sep', 'JOD 78.00'), row('Then monthly', 'JOD 78.00'),
          D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9 }, 'Her renewal date returns to the 24th. One freeze month goes back to her allowance.')
        ])
      ]), { marginTop: 14 }),
      D({ marginTop: 16 }, prim('Restart her membership', function () { v.act('flash', 'Restarted 1 Sep · access on'); v.openScreen('ADM-MEM-04'); }, true))
    ]);
  };

  S['ADM-MSH-06'] = function (v) {
    return dPage([
      h1('Move Dana to Club', 'From Club+ · JOD 78.00'),
      card(D({ padding: '15px 17px', maxWidth: 560, borderColor: C.err }, [
        eyebrow('WHAT SHE LOSES', C.err),
        D({ font: '400 13.5px/1.8 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Access to Abdoun and Sweifieh\nTwo PT sessions a month\nHer three unused PT credits expire 30 days after the change')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560, background: C.sunk }, [
        row('From 24 September', 'JOD 55.00'), row('She saves monthly', 'JOD 23.00'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9, paddingTop: 9, borderTop: '1px solid ' + C.hair }, 'Takes effect at her next renewal, not today — she keeps Club+ for the month she has paid for.')
      ]), { marginTop: 12 }),
      card(D({ padding: '13px 15px', maxWidth: 560 }, [
        eyebrow('TYPE HER MEMBER ID TO CONFIRM', C.err),
        D({ marginTop: 9 }, field('Member ID', 'M-02914'))
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Move her to Club', function () { v.act('flash', 'Scheduled for 24 Sep · Dana notified'); }, true))
    ]);
  };

  S['ADM-MSH-09'] = function (v) {
    return dPage([
      h1('Plans and pricing', 'Nadi Group · 3 plans'),
      table(['PLAN', 'PRICE', 'MEMBERS', 'LAST CHANGED'], [
        ['Flex', 'JOD 40.00', '612', 'Jan 2026'],
        ['Club', 'JOD 58.00', '3,104', '1 Aug 2026'],
        ['Club+', 'JOD 78.00', '1,096', 'Jan 2026']
      ], function () { v.act('flash', 'Plan editor'); }),
      card(D({ padding: '15px 16px', maxWidth: 620, borderColor: C.warn }, [
        eyebrow('CLUB WENT UP THIS MONTH', C.warn),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'JOD 55.00 to JOD 58.00, effective 1 August. 3,104 members are on this plan — 847 renew before the end of September and each must be told before their renewal goes through.'),
        D({ marginTop: 12 }, sec('See who renews next', function () { v.openScreen('ADM-MEM-05'); }, true))
      ]), { marginTop: 14 })
    ]);
  };


  S['ADM-PAY-02'] = function (v) {
    return dPage([
      h1('Refund JOD 28.00', 'Whey 1kg · Ahmad Nabulsi · sold 2 hours ago'),
      card(D({ padding: '15px 17px', maxWidth: 560 }, [
        row('Original sale', 'JOD 28.00'), row('Paid by', 'Visa ···4417'), row('Goes back to', 'the same card'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 10, paddingTop: 10, borderTop: '1px solid ' + C.hair }, 'Three to five days to appear on his statement. The sale stays on record — this creates a linked credit note, it does not edit history.')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560, borderColor: C.err }, [
        eyebrow('TYPE THE AMOUNT TO CONFIRM', C.err),
        D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26', marginTop: 6 }, 'The number is the thing being risked, so you type it rather than clicking yes.'),
        D({ marginTop: 11 }, field('Amount', '28.00')),
        D({ marginTop: 11 }, field('Reason', 'Wrong flavour, unopened'))
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, D({ display: 'flex', gap: 9, flexWrap: 'wrap' }, [
        Btn(function () { v.act('flash', 'Refunded JOD 28.00 · credit note CN-4471'); }, { font: '500 13px/1 ' + sans, background: C.err, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Refund JOD 28.00'),
        sec('Cancel', function () { v.openScreen('ADM-PAY-01'); }, true)
      ]))
    ]);
  };

  S['ADM-PAY-04'] = function (v) {
    return dPage([
      h1('Take payment', 'Ahmad Nabulsi · owes JOD 55.00'),
      card(D({ padding: '15px 17px', maxWidth: 560 }, [
        field('Amount', 'JOD 55.00'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 8 }, 'Editable down for a part payment. Anything over 55.00 goes to his wallet — that will be stated before you confirm.')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560 }, [
        eyebrow('HOW'),
        D({ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }, [
          Btn(function () {}, { font: '500 13px/1 ' + sans, background: C.t1, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Card'),
          sec('Cash', function () {}, true), sec('CliQ', function () {}, true), sec('Wallet · 0.00', function () {}, true)
        ])
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 17px', maxWidth: 560, background: C.sunk }, [
        eyebrow('WHAT THIS SETTLES'),
        D({ font: '400 13px/1.75 ' + sans, color: '#2c2a26', marginTop: 6 }, 'INV-20418 · August · JOD 55.00 · fully paid'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 8 }, 'One open invoice, so allocation is unambiguous. With two or more you choose, and the split is shown before you confirm.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Take JOD 55.00 by card', function () { v.openScreen('POS-02'); }, true))
    ]);
  };

  S['ADM-PAY-06'] = function (v) {
    return dPage([
      h1('When a payment fails', 'Nadi Group · all clubs'),
      card([
        ruleRow('WE TRY AGAIN', 'Twice — the next morning, then 48 hours later. After that we stop and tell someone.'),
        ruleRow('THEY KEEP TRAINING', 'For 14 days after the first failure. Access is never cut by an automation.'),
        ruleRow('WE MESSAGE THEM', 'A draft is prepared after the second failure. It waits for a person to approve it.'),
        ruleRow('WE NEVER', 'Cancel a membership, charge a fee, or block entry. Only a person does those.')
      ], { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Written as sentences rather than a rules engine, because an owner has to be able to read this back and recognise their own policy. The NEVER block is not configurable downward.')), { marginTop: 12 }),
      D({ marginTop: 14 }, sec('Change the retry schedule', function () { v.act('flash', 'Editor · Owner and Accountant only'); }, true))
    ]);
  };

  S['ADM-PAY-07'] = function (v) {
    return dPage([
      h1('Wallets and credits', '184 members hold a balance'),
      table(['MEMBER', 'BALANCE', 'ORIGIN', 'EXPIRES'], [
        ['Dana Qasem', 'JOD 12.50', 'Yoga cancelled 14 Aug', '14 Nov'],
        ['Hala Barakat', 'JOD 8.00', 'Top-up', 'no expiry'],
        ['Lina Haddad', 'JOD 23.00', 'Class credits ×2', '2 Oct'],
        ['Faris Alami', 'JOD 5.00', 'Goodwill · Ziad', '1 Sep']
      ], function () { v.openScreen('ADM-MEM-02'); }),
      card(D({ padding: '15px 16px', maxWidth: 620 }, [
        eyebrow('TOTAL HELD'),
        D({ font: '500 22px/1.15 ' + mono, marginTop: 7 }, 'JOD 2,418.50'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 7 }, 'This is money owed to members, not revenue. Adding a manual credit is a tier-3 action with your name on it.')
      ]), { marginTop: 14 })
    ]);
  };

  S['ADM-PAY-08'] = function (v) {
    return dPage([
      h1('Partial refund', 'INV-19871 · PT 10 sessions · JOD 280.00'),
      card(D({ padding: '15px 17px', maxWidth: 560 }, [
        row('Original', 'JOD 280.00'), row('Sessions used', '7 of 10'), row('Already refunded', 'JOD 0.00'),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 11, paddingTop: 11, borderTop: '1px solid ' + C.line }, [
          D({ font: '500 13.5px/1.4 ' + sans }, 'Refundable'), D({ font: '500 16px/1.15 ' + mono }, 'JOD 84.00')
        ])
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560, borderColor: C.err }, [
        eyebrow('TYPE THE AMOUNT', C.err),
        D({ marginTop: 9 }, field('Refund', '84.00')),
        D({ marginTop: 11 }, field('Reason', 'Moving abroad, 3 sessions unused')),
        D({ font: '400 12px/1.6 ' + sans, color: C.t2, marginTop: 9 }, 'Must be more than zero and no more than 84.00. Three credits are removed from his record when this goes through.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, D({ display: 'flex', gap: 9, flexWrap: 'wrap' }, [
        Btn(function () { v.act('flash', 'Refunded JOD 84.00 · 3 credits removed'); }, { font: '500 13px/1 ' + sans, background: C.err, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Refund JOD 84.00'),
        sec('Cancel', function () {}, true)
      ]))
    ]);
  };

  S['ADM-PAY-09'] = function (v) {
    return dPage([
      h1('Cash reconciliation', 'Khalda · Layla · 16:00–22:00'),
      card(D({ padding: '16px 17px', maxWidth: 560 }, [
        row('Opening float', 'JOD 50.00'), row('Cash sales', 'JOD 96.00'), row('Cash refunds', 'JOD 0.00'),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 11, paddingTop: 11, borderTop: '1px solid ' + C.line }, [
          D({ font: '500 14px/1.4 ' + sans }, 'Should be in the drawer'), D({ font: '500 18px/1.15 ' + mono }, 'JOD 146.00')
        ])
      ]), { marginTop: 14 }),
      card(D({ padding: '16px 17px', maxWidth: 560 }, [
        eyebrow('COUNTED'),
        D({ marginTop: 9 }, field('Amount', '141.00')),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 12, paddingTop: 12, borderTop: '1px solid ' + C.line }, [
          D({ font: '500 13.5px/1.4 ' + sans, color: C.err }, 'Short by'), D({ font: '500 16px/1.15 ' + mono, color: C.err }, 'JOD 5.00')
        ]),
        D({ marginTop: 11 }, field('What happened', 'Gave change from the wrong note on the 18:40 sale')),
        D({ font: '400 12px/1.6 ' + sans, color: C.t2, marginTop: 9 }, 'Anything over JOD 2.00 needs a note. Over JOD 20.00 needs Ziad to countersign.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Close the shift', function () { v.act('flash', 'Closed · JOD 5.00 short, noted, report sent to Ziad'); }, true))
    ]);
  };

  S['ADM-PAY-10'] = function (v) {
    return dPage([
      D({ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }, [
        D({ flex: 1, minWidth: 220 }, [D({ font: '500 22px/1.2 ' + sans, letterSpacing: '-.015em' }, 'Disputed charge'), D({ font: '400 12.5px/1.55 ' + sans, color: C.t2, marginTop: 4 }, 'INV-20194 · Faris Alami · JOD 45.00 · raised 16 August')]),
        badge('EVIDENCE DUE 23 AUG', C.err)
      ]),
      card(D({ padding: '15px 17px', maxWidth: 620, borderColor: C.err }, [
        D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26' }, 'His bank says he did not authorise this. The JOD 45.00 is held by the provider until this is settled — it is not in your account and not lost.'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9, paddingTop: 9, borderTop: '1px solid ' + C.hair }, 'Seven days to respond. No response means the money goes back automatically.')
      ]), { marginTop: 14 }),
      card([
        D({ padding: '11px 15px', background: C.sunk, font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'WHAT WE CAN SHOW'),
        evRow('Signed membership agreement', true),
        evRow('His check-ins during the billing period · 11 visits', true),
        evRow('The receipt sent to his WhatsApp, delivered and read', true),
        evRow('A record of him disputing this before', false)
      ], { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Submit the evidence', function () { v.act('flash', 'Submitted · provider replies within 14 days'); }, true))
    ]);
  };

  S['ADM-POS-01'] = function (v) {
    return dPage([
      h1('Products', '34 items · 3 clubs'),
      filterBar(['All 34', 'Low stock', 'Retail', 'Memberships']),
      table(['PRODUCT', 'PRICE', 'TAX', 'KHALDA', 'ABDOUN'], [
        ['Water 500ml', 'JOD 0.50', '16%', '148', '96'],
        ['Protein bar', 'JOD 2.00', '16%', '62', '41'],
        ['Whey 1kg', 'JOD 28.00', '16%', '14', '9'],
        ['Creatine 300g', 'JOD 22.00', '16%', { t: '0 · OUT', c: C.err }, '6'],
        ['Shaker', 'JOD 6.00', '16%', '31', '18'],
        ['Towel hire', 'JOD 1.00', '16%', '—', '—']
      ], function () { v.act('flash', 'Product editor'); }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Memberships are tax-exempt in Jordan and appear in a separate group. Price changes need an effective date and state how many members are affected.')
    ]);
  };

  S['ADM-POS-02'] = function (v) {
    return dPage([
      h1('Stock', 'Khalda · 1 item out, 2 low'),
      table(['ITEM', 'IN STOCK', 'REORDER AT', 'STATE'], [
        ['Creatine 300g', '0', '6', { t: 'OUT', c: C.err }],
        ['Whey 1kg', '14', '10', { t: 'OK', c: C.t2 }],
        ['Protein bar', '62', '40', { t: 'OK', c: C.t2 }],
        ['Shaker', '4', '8', { t: 'LOW', c: C.warn }],
        ['Water 500ml', '148', '60', { t: 'OK', c: C.t2 }],
        ['Towel', '7', '12', { t: 'LOW', c: C.warn }]
      ], function () { v.act('flash', 'Stock adjustment'); }),
      card(D({ padding: '15px 16px', maxWidth: 620, borderColor: C.err }, [
        eyebrow('CREATINE HAS BEEN OUT FOR 4 DAYS', C.err),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'It is greyed out at the till rather than hidden, so staff can tell a member it is coming rather than that it does not exist. Nine were sold the week before it ran out.'),
        D({ marginTop: 12 }, prim('Order 24', function () { v.act('flash', 'Ordered'); }, true))
      ]), { marginTop: 14 })
    ]);
  };

  S['ADM-POS-03'] = function (v) {
    return dPage([
      h1('Discounts', '4 rules · Nadi Group'),
      card([
        ruleRow('STAFF', '30% off retail. Any staff member can apply it to themselves.'),
        ruleRow('CORPORATE · ARAMEX', '15% off memberships for verified employees. Sales can apply it.'),
        ruleRow('OPEN DAY · EXPIRED 12 AUG', 'Was 20% off the first month. No longer available.'),
        ruleRow('ANYTHING ELSE', 'Up to 10% at a manager\u2019s discretion. Above 10% needs Rania.')
      ], { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'The 10% threshold is what makes the till ask for a manager. Change it here and every POS terminal follows immediately.')), { marginTop: 12 })
    ]);
  };


  S['ADM-SCH-03'] = function (v) {
    return dPage([
      h1('Edit Thursday spin', '19:00 · Studio 2 · 18 booked'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Class', 'Spin'), field('Coach', 'Unassigned'), field('Room', 'Studio 2 · 20 bikes'), field('Repeats', 'Every Thursday')
      ])), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560, borderColor: C.warn }, [
        eyebrow('18 PEOPLE HAVE BOOKED THIS', C.warn),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Changing the time or room notifies all eighteen. Changing the coach does not — members book the class, not the person, unless it is a PT slot.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Save', function () { v.act('flash', 'Saved · nobody needed telling'); v.openScreen('ADM-SCH-02'); }, true))
    ]);
  };

  S['ADM-SCH-04'] = function (v) {
    var days = [['Monday', '08:00–18:00', ''], ['Tuesday', '08:00–18:00', ''], ['Wednesday', '08:00–18:00', ''], ['Thursday', '08:00–18:00', 'Spin 19:00 added'], ['Friday', '08:00–14:00', ''], ['Saturday', '09:00–13:00', ''], ['Sunday', 'Not working', '']];
    return dPage([
      h1('Yousef Haddad · availability', 'Khalda · 9 sessions booked this week'),
      card(days.map(function (r, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '450 13px/1.4 ' + sans, width: 96, flexShrink: 0 }, r[0]),
          D({ font: '400 12.5px/1.4 ' + mono, color: r[1] === 'Not working' ? C.t3 : C.t1, flex: 1 }, r[1]),
          r[2] ? D({ font: '400 11px/1.4 ' + sans, color: C.warn }, r[2]) : null
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'The Thursday spin sits outside his stated hours. It was offered and he accepted, so it stands — but it is flagged rather than silently absorbed.')), { marginTop: 12 })
    ]);
  };

  S['ADM-SCH-05'] = function (v) {
    return dPage([
      h1('Book a PT session', 'Ahmad Nabulsi with Yousef'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Member', 'Ahmad Nabulsi'), field('Coach', 'Yousef Haddad'), field('When', 'Wednesday 26 August, 09:45')
      ])), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560, background: C.sunk }, [
        row('Credits he has', '3'), row('This session uses', '1'), row('Left afterwards', '2'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9, paddingTop: 9, borderTop: '1px solid ' + C.hair }, 'His credits expire in November. With none left this screen offers to sell a package rather than refusing.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Book it', function () { v.act('flash', 'Booked · 2 credits left · both notified'); }, true))
    ]);
  };

  S['ADM-SCH-06'] = function (v) {
    return dPage([
      h1('Rooms', 'Khalda · 4 spaces'),
      table(['ROOM', 'HOLDS', 'EQUIPMENT', 'IN USE TODAY'], [
        ['Studio 1', '24', 'Mats, mirrors', '6 classes'],
        ['Studio 2', '20', '20 bikes', '4 classes'],
        ['Main floor', '120', 'Free weights, machines', 'open'],
        ['PT room', '2', 'Platform, rack', '9 sessions']
      ], function () { v.act('flash', 'Room editor'); }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Capacity here is what stops a class being overbooked and what makes double-booking impossible when a class is created. It is a constraint, not a label.')), { marginTop: 14 })
    ]);
  };

  S['ADM-SCH-07'] = function (v) {
    return dPage([
      h1('Cancel Thursday spin', '19:00 · 18 members booked'),
      card(D({ padding: '15px 17px', maxWidth: 620, borderColor: C.err }, [
        eyebrow('YOU MUST TELL THEM SOMETHING', C.err),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'This cannot go through without a message and a choice for each member. A class that vanishes silently is the most damaging thing this screen could allow.'),
        D({ marginTop: 11 }, field('What happened', 'No coach available — our mistake, sorry'))
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 620 }, [
        eyebrow('AND OFFER THEM'),
        D({ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }, [
          Btn(function () {}, { font: '500 13px/1 ' + sans, background: C.t1, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Friday 19:00 instead'),
          sec('JOD 12.50 credit each', function () {}, true)
        ]),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 10 }, 'Friday has 6 free bikes, so 12 of the 18 would need the credit anyway. Sent in each member\u2019s own language.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Cancel and notify all 18', function () { v.act('flash', 'Cancelled · 6 moved to Friday, 12 credited'); v.openScreen('ADM-SCH-01'); }, true))
    ]);
  };

  S['ADM-ACC-01'] = function (v) {
    var dev = [['Khalda · turnstile 1', 'Working', '61 entries today', C.ok], ['Khalda · turnstile 2', 'Working', '58 entries today', C.ok], ['Sweifieh · turnstile 1', 'Not responding', 'since 09:04', C.err], ['Sweifieh · turnstile 2', 'Working', '23 entries today', C.ok], ['Abdoun · turnstile 1', 'Working', '141 entries today', C.ok]];
    return dPage([
      h1('Access', 'One device down · 3 clubs'),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('ENTRIES TODAY', '283', 'across 3 clubs'),
        metric('TURNED AWAY', '7', '4 during the outage'),
        metric('DEVICES', '4 of 5', 'responding')
      ]),
      card(dev.map(function (r, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', borderTop: i ? '1px solid ' + C.hair : 'none' }, [
          D({ font: '450 13px/1.4 ' + sans, flex: 1, minWidth: 140 }, r[0]),
          D({ font: '500 11.5px/1.4 ' + mono, color: r[3], width: 120 }, r[1]),
          D({ font: '400 11px/1.4 ' + mono, color: C.t2 }, r[2])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '13px 15px', borderColor: C.err }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Sweifieh turnstile 1 has been down for 16 minutes. Members are entering through turnstile 2 and the desk, and every entry is recorded. Nothing is lost — this is a queue at the door, not a data problem.')), { marginTop: 12 })
    ]);
  };

  S['ADM-ACC-02'] = function (v) {
    return dPage([
      h1('Turned away', '7 today · all clubs'),
      table(['WHEN', 'MEMBER', 'WHERE', 'WHY'], [
        ['18:39', 'Tareq Odeh', 'Khalda', { t: 'MEMBERSHIP ENDED', c: C.err }],
        ['09:11', 'Nour Khoury', 'Sweifieh', { t: 'DEVICE DOWN', c: C.warn }],
        ['09:09', 'Rami Saleh', 'Sweifieh', { t: 'DEVICE DOWN', c: C.warn }],
        ['09:07', 'Hala Barakat', 'Sweifieh', { t: 'DEVICE DOWN', c: C.warn }],
        ['09:05', 'Sara Amr', 'Sweifieh', { t: 'DEVICE DOWN', c: C.warn }],
        ['08:14', 'Yara Mansour', 'Abdoun', { t: 'FROZEN', c: C.info }],
        ['07:52', 'Omar Zaid', 'Khalda', { t: 'NO CREDENTIAL', c: C.t2 }]
      ], function () { v.openScreen('ADM-MEM-01'); }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Four of these were the Sweifieh fault, not policy — they should be apologised to. Filtering by reason is what separates "our equipment failed" from "their membership ended".')), { marginTop: 14 }),
      D({ marginTop: 14 }, sec('Apologise to the 4', function () { v.act('flash', 'WhatsApp sent to 4 members'); }, true))
    ]);
  };

  S['ADM-ACC-03'] = function (v) {
    return dPage([
      h1('Ahmad Nabulsi · access', 'Card, app and fingerprint'),
      card([
        credRow('Card ···8841', 'Active since March 2024', C.ok, 'Replace'),
        credRow('App pass', 'Active · rotates every 30 seconds', C.ok, 'Revoke'),
        credRow('Fingerprint', 'Enrolled 4 March 2024', C.ok, 'Remove')
      ], { marginTop: 14 }),
      card(D({ padding: '15px 16px', maxWidth: 620, borderColor: C.err }, [
        eyebrow('WHAT WE HOLD, AND WHAT WE DO NOT', C.err),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Only whether a fingerprint is enrolled. Not an image, not a template, not anything exportable. It cannot be viewed on this screen or any other, by any role.'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9 }, 'Removing it needs Rania\u2019s approval and is logged where Ahmad can see it.')
      ]), { marginTop: 12 })
    ]);
  };


  S['ADM-STF-01'] = function (v) {
    return dPage([
      h1('Staff', '24 people · 3 clubs'),
      filterBar(['All 24', 'Khalda', 'Coaches', 'Reception']),
      table(['NAME', 'ROLE', 'CLUBS', 'LAST ACTIVE'], [
        ['Rania Haddad', 'Owner', 'All 3', 'now'],
        ['Ziad Masri', 'Club manager', 'Khalda', '12 min ago'],
        ['Nadia Farah', 'Accountant', 'All 3', '1 hour ago'],
        ['Layla Odeh', 'Reception', 'Khalda', 'now'],
        ['Yousef Haddad', 'Coach', 'Khalda', '20 min ago'],
        ['Omar Sabri', 'Coach', 'Khalda', 'yesterday'],
        ['Dana Nasser', 'Coach', 'Khalda, Abdoun', '2 hours ago']
      ], function () { v.openScreen('ADM-STF-02'); })
    ]);
  };

  S['ADM-STF-02'] = function (v) {
    return dPage([
      memberHeader(v, 'Layla Odeh', 'Reception · Khalda · joined June 2024', null, null),
      card(D({ padding: '15px 17px', maxWidth: 620 }, [
        eyebrow('WHAT SHE CAN DO'),
        D({ font: '400 13px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Check members in and out\nTake payments and sell retail\nBook classes and PT\nSee membership and payment state')
      ]), { marginTop: 16 }),
      card([
        D({ padding: '11px 15px', background: C.sunk, font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'EXTRA PERMISSIONS · GRANTED ONE BY ONE'),
        permRow('Approve refunds', false, 'Ziad does this'),
        permRow('Export member data', false, 'Owner only at this club'),
        permRow('See health notes', false, 'Coaches and nutritionists'),
        permRow('Override a denied entry', true, 'Granted by Ziad, 4 July')
      ], { marginTop: 12 }),
      card(D({ padding: '13px 15px', maxWidth: 620, borderColor: C.err }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Changing a permission is a tier-4 action and needs Rania. You cannot grant a permission you do not hold yourself — Ziad cannot give Layla export rights he does not have.')), { marginTop: 12 })
    ]);
  };

  S['ADM-STF-03'] = function (v) {
    return dPage([
      h1('Invite someone', 'Khalda'),
      card(D({ padding: '16px 18px', maxWidth: 520 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Email', 'sara.q@nadigroup.jo'), field('Role', 'Reception'), field('Clubs', 'Khalda only'), field('Invitation expires', 'In 7 days')
      ])), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 520, background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'She sets her own password and two-factor on first sign-in. Nobody, including you, can see it.')), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Send the invitation', function () { v.act('flash', 'Invited · expires 26 August'); v.openScreen('ADM-STF-01'); }, true))
    ]);
  };

  S['ADM-STF-04'] = function (v) {
    var caps = [['See member records', 'Y Y Y Y Y Y'], ['Take payments', 'Y Y Y Y Y ·'], ['Approve refunds', 'Y Y Y · · ·'], ['Change memberships', 'Y Y Y · Y ·'], ['See health notes', 'Y · · · · Y'], ['Export data', 'Y · Y · · ·'], ['Change permissions', 'Y · · · · ·']];
    return dPage([
      h1('Who can do what', '9 roles · editable per tenant'),
      D({ border: '1px solid ' + C.line, borderRadius: 4, background: C.surf, overflowX: 'auto', marginTop: 14 }, [
        D({ minWidth: 640, display: 'grid', gridTemplateColumns: '220px repeat(6,1fr)', gap: 8, padding: '10px 16px', background: C.sunk, borderBottom: '1px solid ' + C.line }, ['', 'OWNER', 'MGR', 'ACCT', 'RECEP', 'SALES', 'COACH'].map(function (x, i) {
          return D({ key: i, font: '500 8.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.05em' }, x);
        }))
      ].concat(caps.map(function (r, i) {
        return D({ key: i, minWidth: 640, display: 'grid', gridTemplateColumns: '220px repeat(6,1fr)', gap: 8, padding: '11px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', alignItems: 'center' }, [
          D({ font: '400 12px/1.4 ' + sans }, r[0])
        ].concat(r[1].split(' ').map(function (c, j) {
          return D({ key: j, font: '500 11px/1.4 ' + mono, color: c === 'Y' ? C.ok : C.ctl }, c === 'Y' ? '✓' : '·');
        })));
      }))),
      card(D({ padding: '13px 15px', maxWidth: 660, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Changing permissions and starting an impersonation are Owner-only and cannot be delegated, whatever a tenant configures here.')), { marginTop: 14 })
    ]);
  };

  S['ADM-COM-01'] = function (v) {
    var msgs = [['them', 'Hi, is the 19:00 spin on Thursday still running?', 'Ahmad · 18:22'], ['me', "Yes — we're confirming the coach today and I'll message you by this evening.", 'Layla · 18:31 · read'], ['them', 'Great, thanks', 'Ahmad · 18:33']];
    return dPage([
      h1('Ahmad Nabulsi', 'WhatsApp · 079 555 0134'),
      card(D({ padding: '13px 15px', background: C.sunk }, D({ font: '400 12px/1.65 ' + sans, color: '#3d3b36' }, 'Marketing consent withdrawn 12 July. Service messages about payments, bookings and access are still permitted. Promotional templates do not appear below.')), { marginTop: 14 }),
      D({ display: 'flex', flexDirection: 'column', gap: 9, marginTop: 14, maxWidth: 560 }, msgs.map(function (m, i) {
        var mine = m[0] === 'me';
        return D({ key: i, alignSelf: mine ? 'flex-end' : 'flex-start', maxWidth: '80%', background: mine ? C.wash : C.canvas, borderRadius: mine ? '8px 8px 2px 8px' : '8px 8px 8px 2px', padding: '11px 13px' }, [
          D({ font: '400 12.5px/1.6 ' + sans }, m[1]),
          D({ font: '400 10px/1.4 ' + mono, color: C.t2, marginTop: 4 }, m[2])
        ]);
      })),
      D({ display: 'flex', gap: 7, marginTop: 16, flexWrap: 'wrap', maxWidth: 560 }, [sec('Payment link', function () {}), sec('Class confirmed', function () {}), sec('Renewal due', function () {})]),
      D({ display: 'flex', gap: 9, marginTop: 11, alignItems: 'center', maxWidth: 560 }, [
        D({ flex: 1, font: '400 12.5px/1.5 ' + sans, color: C.t3, border: '1px solid ' + C.line, borderRadius: 6, padding: '12px 13px', minHeight: 44, display: 'flex', alignItems: 'center' }, 'Write a reply'),
        prim('Send', function () { v.act('flash', 'Sent'); })
      ]),
      D({ font: '400 11.5px/1.6 ' + sans, color: C.t2, marginTop: 10, maxWidth: 560 }, 'Outside the 24-hour window only approved templates can open a conversation. Free text is disabled and the reason is stated rather than the Send button silently failing.')
    ]);
  };

  S['ADM-COM-02'] = function (v) {
    var t = [['Payment failed', 'Service', 'Approved', C.ok], ['Class cancelled', 'Service', 'Approved', C.ok], ['Renewal reminder', 'Service', 'Approved', C.ok], ['Open day invitation', 'Marketing', 'Approved', C.ok], ['Refer a friend', 'Marketing', 'Waiting on WhatsApp', C.warn]];
    return dPage([
      h1('Message templates', '5 templates · Arabic and English'),
      table(['TEMPLATE', 'KIND', 'STATE'], t.map(function (r) { return [r[0], r[1], { t: r[2], c: r[3] }]; }), function () { v.act('flash', 'Template editor'); }),
      card(D({ padding: '15px 16px', maxWidth: 620 }, [
        eyebrow('WHY APPROVAL IS NOT OURS TO GIVE'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'WhatsApp approves templates, not Veyro. "Refer a friend" has been pending with them for four days. We show their real state rather than pretending it is ready.')
      ]), { marginTop: 14 })
    ]);
  };

  S['ADM-COM-03'] = function (v) {
    return dPage([
      h1('Message a group', 'Khalda'),
      card(D({ padding: '16px 18px', maxWidth: 620 }, [
        eyebrow('WHO'),
        D({ font: '400 14px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Not visited in 30 days · 214 members'),
        D({ display: 'flex', justifyContent: 'space-between', marginTop: 12, paddingTop: 12, borderTop: '1px solid ' + C.line }, [
          D({ font: '500 13.5px/1.4 ' + sans }, 'Will actually receive it'), D({ font: '500 16px/1.15 ' + mono }, '186')
        ]),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.warn, marginTop: 8 }, '28 have withdrawn marketing consent. They are excluded automatically — this is enforced, not a warning you can click past.')
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 620 }, [
        eyebrow('WHAT THEY GET'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6, padding: '11px 13px', background: C.canvas, borderRadius: 4 }, "We haven't seen you at Khalda for a while. Your membership is still active — come in whenever you like, or reply here if something has changed."),
        D({ font: '400 12px/1.6 ' + sans, color: C.t2, marginTop: 9 }, 'Sent in each member\u2019s own language. 121 will receive Arabic, 65 English.')
      ]), { marginTop: 12 }),
      D({ marginTop: 16 }, prim('Send to 186 members', function () { v.act('flash', 'Sending · 186 messages queued'); }, true))
    ]);
  };

  S['ADM-COM-04'] = function (v) {
    var rows = [['A payment fails', 'Y Y Y ·'], ['A membership expires soon', 'Y Y · ·'], ['A class has no coach', 'Y Y · Y'], ['A device stops responding', 'Y Y Y ·'], ['A lead goes 48h without contact', '· Y · ·'], ['A refund is requested', 'Y Y · ·']];
    return dPage([
      h1('Who gets told what', 'Nadi Group'),
      D({ border: '1px solid ' + C.line, borderRadius: 4, background: C.surf, overflowX: 'auto', marginTop: 14 }, [
        D({ minWidth: 560, display: 'grid', gridTemplateColumns: '260px repeat(4,1fr)', gap: 10, padding: '10px 16px', background: C.sunk, borderBottom: '1px solid ' + C.line }, ['', 'OWNER', 'MANAGER', 'ACCOUNTANT', 'COACH'].map(function (x, i) {
          return D({ key: i, font: '500 8.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.05em' }, x);
        }))
      ].concat(rows.map(function (r, i) {
        return D({ key: i, minWidth: 560, display: 'grid', gridTemplateColumns: '260px repeat(4,1fr)', gap: 10, padding: '11px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', alignItems: 'center' }, [
          D({ font: '400 12px/1.4 ' + sans }, r[0])
        ].concat(r[1].split(' ').map(function (c, j) {
          return D({ key: j, font: '500 11px/1.4 ' + mono, color: c === 'Y' ? C.ok : C.ctl }, c === 'Y' ? '✓' : '·');
        })));
      }))),
      card(D({ padding: '13px 15px', maxWidth: 660, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Defaults are deliberately quiet. Nothing opts anyone into a channel they did not choose, and an owner cannot subscribe staff to alerts on their behalf.')), { marginTop: 14 })
    ]);
  };

  S['ADM-TSK-01'] = function (v) {
    var t = [['Call the 5 members who have not visited in 20 days', 'Ziad', 'Today', 'Retention item', C.warn], ['Verify 22 PT sessions', 'Yousef', 'Today', 'Coach queue', C.warn], ['Fix 3 JoFotara invoices', 'Nadia', 'Today', 'Compliance', C.err], ['Order creatine', 'Ziad', 'Tomorrow', 'Low stock', null], ['Renew Layla\u2019s first aid certificate', 'Ziad', '3 Sep', 'Document expiry', null]];
    return dPage([
      h1('Tasks', '5 open · 3 today'),
      filterBar(['Mine', 'Everyone', 'Overdue']),
      card(t.map(function (r, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', flexWrap: 'wrap' }, [
          D({ font: '400 12px/1 ' + mono, color: C.ctl, width: 14 }, '☐'),
          D({ flex: 1, minWidth: 220 }, [
            D({ font: '450 13px/1.4 ' + sans }, r[0]),
            D({ font: '400 11px/1.5 ' + mono, color: C.t2, marginTop: 2 }, r[3] + ' · ' + r[1])
          ]),
          D({ font: '400 11.5px/1.4 ' + mono, color: r[4] || C.t2 }, r[2])
        ]);
      }), { marginTop: 14 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Three of these were created by Veyro from attention items and link back to them. Two were typed by a person.')
    ]);
  };

  S['ADM-AUT-01'] = function (v) {
    var a = [['Failed payment follow-up', 'Active', '412 runs', 'JOD 18,240 recovered', C.ok], ['Renewal reminder, 7 days out', 'Active', '1,104 runs', '84% renewed', C.ok], ['Welcome a new member', 'Active', '284 runs', '—', C.ok], ['Win back after 30 days away', 'Paused', '96 runs', '11% returned', C.warn]];
    return dPage([
      h1('Automations', '3 running · 1 paused'),
      table(['RULE', 'STATE', 'RUNS', 'WHAT IT DID'], a.map(function (r) { return [r[0], { t: r[1], c: r[4] }, r[2], r[3]]; }), function () { v.openScreen('ADM-AUT-02'); }),
      card(D({ padding: '15px 16px', maxWidth: 620 }, [
        eyebrow('WHY THE WIN-BACK IS PAUSED'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Rania paused it in July — 11% is not a good enough return to justify messaging people who have chosen to stay away. The run history is kept so the decision can be revisited with evidence.')
      ]), { marginTop: 14 })
    ]);
  };

  S['ADM-AUT-02'] = function (v) {
    return dPage([
      h1('Failed payment follow-up', 'Active since March · 412 runs'),
      card([
        ruleRow('WHEN', 'A payment fails for any reason.'),
        ruleRow('WE TRY AGAIN', 'The next morning, then 48 hours later. Twice, then we stop.'),
        ruleRow('AFTER THE SECOND FAILURE', 'A message is drafted naming the amount and the reason, with a payment link. It waits for someone to approve it.'),
        ruleRow('THEY KEEP TRAINING', 'For 14 days. Access is never cut by this rule.'),
        ruleRow('WE NEVER', 'Cancel a membership, add a fee, or block entry. A person does those or nobody does.')
      ], { marginTop: 14 }),
      card(D({ padding: '15px 16px', maxWidth: 620, background: C.sunk }, [
        eyebrow('WHAT IT HAS DONE'),
        D({ font: '400 13px/1.75 ' + sans, color: '#2c2a26', marginTop: 6 }, '412 failures handled\n318 recovered without anyone calling\nJOD 18,240 collected\n0 memberships cancelled by this rule')
      ]), { marginTop: 12 }),
      D({ display: 'flex', gap: 9, marginTop: 16, flexWrap: 'wrap' }, [sec('See every run', function () { v.openScreen('ADM-AUT-03'); }), sec('Pause it', function () { v.act('flash', 'Paused'); })])
    ]);
  };

  S['ADM-AUT-03'] = function (v) {
    return dPage([
      h1('Failed payment follow-up · runs', 'Last 48 hours'),
      table(['WHEN', 'MEMBER', 'WHAT HAPPENED', 'RESULT'], [
        ['06:13', 'Ahmad Nabulsi', 'Retry 2 declined · message drafted', { t: 'WAITING FOR APPROVAL', c: C.warn }],
        ['06:12', 'Dana Qasem', 'Retry 2 declined · message drafted', { t: 'WAITING FOR APPROVAL', c: C.warn }],
        ['Yesterday', 'Hala Barakat', 'Retry 1 succeeded', { t: 'RECOVERED', c: C.ok }],
        ['Yesterday', 'Omar Zaid', 'Retry 1 succeeded', { t: 'RECOVERED', c: C.ok }],
        ['2 days ago', 'Nour Khoury', 'Link opened, paid', { t: 'RECOVERED', c: C.ok }]
      ], function () { v.openScreen('ADM-PAY-05'); }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'This is how a manager audits something they cannot watch happening. Two drafts are waiting — the automation stops short of sending on its own, by design.')
    ]);
  };


  S['ADM-RPT-01'] = function (v) {
    var r = [['Revenue', 'What came in, by club and plan', 'ADM-RPT-02'], ['Membership', 'Who joined, who left, who stayed', 'ADM-RPT-03'], ['Attendance', 'When the gym is busy', 'ADM-RPT-04'], ['Coaching', 'Sessions delivered and verified', 'ADM-RPT-01'], ['Retail', 'What sells and what sits', 'ADM-RPT-01']];
    return dPage([
      h1('Reports', 'Five available to you'),
      card(r.map(function (x, i) {
        return Btn(function () { v.openScreen(x[2]); }, { display: 'flex', gap: 12, alignItems: 'center', padding: '15px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
          D({ flex: 1 }, [D({ font: '450 14px/1.4 ' + sans }, x[0]), D({ font: '400 12px/1.55 ' + sans, color: C.t2, marginTop: 2 }, x[1])])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Nadia sees the financial reports. Ziad sees the operational ones for Khalda. Neither is shown a list of reports they cannot open.')), { marginTop: 14 })
    ]);
  };

  S['ADM-RPT-02'] = function (v) {
    return dPage([
      h1('Revenue', 'August to date · all clubs'),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('COLLECTED', 'JOD 41,280.00', 'down 7.8% on July'),
        metric('MEMBERSHIPS', 'JOD 34,110.00', '83% of the total'),
        metric('PERSONAL TRAINING', 'JOD 5,420.00', 'down 1,840'),
        metric('RETAIL', 'JOD 1,750.00', 'up 4%')
      ]),
      card(D({ padding: '15px 16px' }, [
        eyebrow('BY CLUB'),
        D({ marginTop: 11 }, [
          barRow('Abdoun', 'JOD 17,940', '+2.1%', 100, C.t2),
          barRow('Khalda', 'JOD 14,110', '−18.4%', 79, C.err),
          barRow('Sweifieh', 'JOD 9,230', '+5.6%', 51, C.t2)
        ])
      ]), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620 }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Khalda accounts for the entire shortfall — the unverified PT sessions are most of it. Abdoun and Sweifieh are both ahead of July.')), { marginTop: 12 }),
      D({ marginTop: 14 }, sec('Export · needs a reason', function () { v.openScreen('ADM-RPT-05'); }, true))
    ]);
  };

  S['ADM-RPT-03'] = function (v) {
    return dPage([
      h1('Membership', 'August to date'),
      D({ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 1, background: C.line, border: '1px solid ' + C.line, borderRadius: 4, overflow: 'hidden', marginTop: 14 }, [
        metric('JOINED', '61', ''), metric('LEFT', '23', ''), metric('NET', '+38', 'now 4,812'), metric('STAYED A YEAR', '68%', 'of last August\u2019s joiners')
      ]),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHY THE 23 LEFT'),
        D({ marginTop: 11 }, [
          barRow('Moved away', '8', '35%', 100, C.t2),
          barRow('Too expensive', '6', '26%', 75, C.warn),
          barRow('Not using it', '5', '22%', 62, C.t2),
          barRow('Unhappy', '2', '9%', 25, C.err),
          barRow('No reason given', '2', '9%', 25, C.t2)
        ])
      ]), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620 }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Six left over price in the month Club went up by JOD 3.00. Worth watching next month before drawing a conclusion from one data point.')), { marginTop: 12 })
    ]);
  };

  S['ADM-RPT-04'] = function (v) {
    var hours = [['06', 12], ['08', 41], ['10', 28], ['12', 34], ['14', 22], ['16', 48], ['18', 96], ['20', 71], ['22', 18]];
    return dPage([
      h1('Attendance', 'Khalda · last 30 days'),
      card(D({ padding: '15px 16px' }, [
        eyebrow('WHEN PEOPLE COME'),
        D({ display: 'flex', alignItems: 'flex-end', gap: 6, height: 90, marginTop: 14 }, hours.map(function (x, i) {
          return D({ key: i, flex: 1 }, [
            D({ height: Math.round(x[1] / 96 * 76) + 'px', background: x[1] > 70 ? C.warn : '#cbc6bc', borderRadius: 1 }),
            D({ font: '400 9px/1.4 ' + mono, color: C.t2, marginTop: 5, textAlign: 'center' }, x[0])
          ]);
        }))
      ]), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620 }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, '18:00 to 20:00 runs at 96 people against a floor capacity of 180 — comfortable. The 19:00 spin is the constraint, not the building: 20 bikes against a class that fills at 92% every week.')), { marginTop: 12 })
    ]);
  };

  S['ADM-RPT-05'] = function (v) {
    return dPage([
      h1('Export revenue data', 'August · all clubs'),
      card(D({ padding: '15px 17px', maxWidth: 560, borderColor: C.err }, [
        eyebrow('THIS CONTAINS PERSONAL AND FINANCIAL DATA', C.err),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, '4,812 member names, amounts and payment methods. Once it leaves Veyro it is on your device and your responsibility.'),
        D({ marginTop: 11 }, field('Why do you need it', 'Quarterly review with the accountant')),
        D({ font: '400 12px/1.6 ' + sans, color: C.t2, marginTop: 9 }, 'Your name, the reason and the time are recorded in the audit log, which Rania can read.')
      ]), { marginTop: 14 }),
      D({ marginTop: 16 }, D({ display: 'flex', gap: 9, flexWrap: 'wrap' }, [
        Btn(function () { v.act('flash', 'Exported · logged'); }, { font: '500 13px/1 ' + sans, background: C.err, color: C.surf, padding: '13px 15px', borderRadius: 6, minHeight: 44, display: 'inline-flex', alignItems: 'center' }, 'Export as CSV'),
        sec('Cancel', function () { v.openScreen('ADM-RPT-02'); }, true)
      ]))
    ]);
  };

  S['ADM-SET-01'] = function (v) {
    return dPage([
      h1('Organisation', 'Nadi Group'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Legal name', 'Nadi Group for Sports Services LLC'),
        field('Trading name', 'Nadi Group'),
        field('Registered address', 'Abdoun Circle, Amman 11183, Jordan'),
        field('Tax number', '1099238471'),
        field('Contact', 'rania@nadigroup.jo · 06 592 1100')
      ])), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 560, background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'The legal name and tax number appear on every invoice and every JoFotara submission. Changing them changes documents already issued going forward, not retrospectively.')), { marginTop: 12 })
    ]);
  };

  S['ADM-SET-02'] = function (v) {
    return dPage([
      h1('Khalda', 'One of three clubs'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Address', 'Khalda, Amman'),
        field('Opening hours', 'Sat–Thu 06:00–23:00 · Fri 08:00–22:00'),
        field('Floor capacity', '180'),
        field('Phone', '06 592 1120')
      ])), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 560, background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'Friday hours differ because of prayers — the schedule and the booking engine both read this rather than assuming a Monday-to-Sunday week.')), { marginTop: 12 })
    ]);
  };

  S['ADM-SET-04'] = function (v) {
    return dPage([
      h1('How money comes in', 'Nadi Group · Jordan'),
      card([
        intRow('Card payments', 'Connected · Network International', 'Last settled this morning', C.ok),
        intRow('CliQ', 'Connected · Arab Bank', 'Instant transfers from member phones', C.ok),
        intRow('Cash', 'Enabled at all 3 clubs', 'Reconciled per shift', C.ok)
      ], { marginTop: 14 }),
      card(D({ padding: '15px 16px', maxWidth: 620, borderColor: C.warn }, [
        eyebrow('WHEN THE CARD READER CANNOT BE REACHED', C.warn),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Sales queue locally and submit when the connection returns. The receipt says "payment pending" rather than "paid" — telling a member they have paid before the bank confirms is the one error this must never make.'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9 }, 'Cash and CliQ are unaffected and keep working.')
      ]), { marginTop: 12 })
    ]);
  };

  S['ADM-SET-05'] = function (v) {
    var i = [['JoFotara', 'e-invoicing · Jordan', 'Submitting since June', C.ok], ['WhatsApp Business', 'Member messaging', '8,412 sent this month', C.ok], ['Network International', 'Card payments', 'Healthy', C.ok], ['CliQ · Arab Bank', 'Bank transfers', 'Healthy', C.ok], ['Access hardware', '5 turnstiles', '1 not responding', C.err]];
    return dPage([
      h1('Connected services', '5 · one needs attention'),
      card(i.map(function (x, n) {
        return D({ key: n, display: 'flex', gap: 12, alignItems: 'center', padding: '14px 16px', borderTop: n ? '1px solid ' + C.hair : 'none', flexWrap: 'wrap' }, [
          D({ flex: 1, minWidth: 180 }, [D({ font: '450 13.5px/1.4 ' + sans }, x[0]), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, x[1])]),
          D({ font: '400 11.5px/1.4 ' + mono, color: x[3], width: 170 }, x[2])
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'Disconnecting anything here states what stops working first. Removing WhatsApp, for example, stops payment links and class notifications — not just messaging.')), { marginTop: 12 })
    ]);
  };

  S['ADM-SET-06'] = function (v) {
    return dPage([
      h1('Your brand', 'Nadi Group'),
      card(D({ padding: '16px 18px', maxWidth: 620 }, [
        eyebrow('YOUR COLOUR'),
        D({ display: 'flex', gap: 10, marginTop: 11, alignItems: 'center', flexWrap: 'wrap' }, [
          D({ width: 46, height: 46, borderRadius: 6, background: '#1b4079', border: '1px solid rgba(0,0,0,.12)' }),
          D({ flex: 1, minWidth: 200 }, [D({ font: '400 12.5px/1.6 ' + mono }, '#1b4079'), D({ font: '400 12px/1.6 ' + sans, color: C.ok, marginTop: 3 }, 'Passes · 10.13:1 on white, clearly different from every status colour')])
        ])
      ]), { marginTop: 14 }),
      card(D({ padding: '15px 16px', maxWidth: 620, borderColor: C.warn }, [
        eyebrow('WHAT YOUR COLOUR CANNOT BECOME', C.warn),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'It cannot be used for paid, failed, overdue or frozen, and it cannot be the colour of Veyro\u2019s AI. If you pick a green close to the one we use for confirmed payments, we will say so and offer the nearest shade that works.'),
        D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 9 }, 'A member misreading a failed payment as paid is worse than a brand being slightly off.')
      ]), { marginTop: 12 }),
      card(D({ padding: '15px 16px', maxWidth: 620 }, [
        eyebrow('LOGO'),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'Full colour and a single-colour version. The second one is required — it is what appears on receipts, invoices and printed exports.')
      ]), { marginTop: 12 })
    ]);
  };

  S['ADM-SET-07'] = function (v) {
    return dPage([
      h1('Language and formats', 'Nadi Group'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Languages offered', 'Arabic and English'),
        field('Default for new members', 'Arabic'),
        field('Numerals', 'Arabic-Indic · ٠١٢٣'),
        field('Money', 'Latin digits with JOD · JOD 55.00'),
        field('Dates', 'Levantine month names · آب, أيلول'),
        field('Week starts', 'Saturday')
      ])), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 560, background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'Money keeps Latin digits even in Arabic, because that is the form on your invoices and JoFotara submissions. A member disputing a charge must see the same string in both places.')), { marginTop: 12 })
    ]);
  };

  S['ADM-SET-08'] = function (v) {
    return dPage([
      h1('Security', 'Nadi Group · 24 staff accounts'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Two-factor', 'Required for everyone'),
        field('Signed out after', '8 hours idle · 15 minutes on shared devices'),
        field('Re-confirm password before', 'Refunds, exports, permission changes')
      ])), { marginTop: 14 }),
      card([
        D({ padding: '11px 15px', background: C.sunk, font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em' }, 'RECENT'),
        tl('09:12 today', 'Veyro support opened your data', 'Read only · ticket #4182 · 21 minutes'),
        tl('08:41 today', 'Nadia granted refund approval', 'By Rania'),
        tl('Yesterday', 'Ziad approved a refund', 'JOD 28.00 · Khalda')
      ], { marginTop: 12 }),
      card(D({ padding: '13px 15px', maxWidth: 620 }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'You can read every time Veyro staff opened your data, why, and for how long. That entry is written by us and cannot be removed by us.')), { marginTop: 12 })
    ]);
  };

  S['ADM-AUTH-01'] = function (v) {
    return dPage([
      D({ maxWidth: 380, margin: '40px auto 0' }, [
        D({ width: 26, height: 26, borderRadius: 5, background: C.t1, color: C.surf, font: '500 14px/26px ' + sans, textAlign: 'center' }, 'V'),
        D({ font: '500 24px/1.18 ' + sans, letterSpacing: '-.018em', marginTop: 18 }, 'Sign in'),
        D({ font: '400 13px/1.6 ' + sans, color: C.t2, marginTop: 5 }, 'Nadi Group'),
        D({ display: 'flex', flexDirection: 'column', gap: 11, marginTop: 20 }, [field('Email', 'ziad@nadigroup.jo'), field('Password', '••••••••••')]),
        D({ marginTop: 16 }, prim('Continue', function () { v.openScreen('ADM-CC-02'); }, true)),
        D({ font: '400 12px/1.65 ' + sans, color: C.t2, marginTop: 14 }, 'A code from your phone comes next. If the email or password is wrong we say so without telling you which — that is deliberate.')
      ])
    ]);
  };

  S['ADM-AUTH-02'] = function (v) {
    return dPage([
      D({ maxWidth: 420, margin: '30px auto 0' }, [
        badge('CONFIRM IT IS YOU', C.err),
        D({ font: '500 22px/1.2 ' + sans, letterSpacing: '-.015em', marginTop: 12 }, 'Refunding JOD 84.00'),
        D({ font: '400 13.5px/1.7 ' + sans, color: '#2c2a26', marginTop: 8 }, 'You signed in four hours ago. Anything that moves money needs your password again — it takes a second and it means a borrowed screen cannot issue refunds.'),
        D({ marginTop: 18 }, field('Password', '••••••••••')),
        D({ marginTop: 16 }, prim('Confirm and refund', function () { v.act('flash', 'Confirmed · refund processed'); }, true)),
        D({ marginTop: 9 }, sec('Go back', function () { v.openScreen('ADM-PAY-08'); }, true)),
        D({ font: '400 12px/1.65 ' + sans, color: C.t2, marginTop: 14 }, 'Cancelling returns you to the refund, not to the beginning.')
      ])
    ]);
  };

  S['ADM-AI-01'] = function (v) {
    return dPage([
      D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [
        D({ font: '400 11px/1 ' + mono, color: '#4a3d7a' }, '✦'),
        D({ font: '500 10px/1.4 ' + mono, color: '#4a3d7a', letterSpacing: '.07em' }, 'HOW VEYRO REACHED THIS')
      ]),
      D({ font: '500 22px/1.2 ' + sans, letterSpacing: '-.015em', marginTop: 10 }, 'PT revenue at Khalda is down JOD 1,840'),
      card(D({ padding: '15px 17px', maxWidth: 660 }, [
        eyebrow('WHAT WE READ'),
        D({ font: '400 13px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, 'PT session records, 1–19 August, Khalda · 214 rows\nOmar Sabri\u2019s roster and hours, July and August\nPT invoices for the same period · 96 rows'),
        D({ font: '500 9.5px/1.4 ' + mono, color: C.t2, letterSpacing: '.07em', marginTop: 14 }, 'WHAT THE NUMBERS SAY'),
        D({ font: '400 13px/1.85 ' + sans, color: '#2c2a26', marginTop: 6 }, '31 sessions delivered with no verification, so never invoiced · JOD 1,240\nOmar\u2019s roster fell from 14 clients to 9 when he cut his hours\nHis remaining 9 booked 22% less often than in July')
      ]), { marginTop: 16 }),
      card(D({ padding: '15px 17px', maxWidth: 660 }, [
        eyebrow('WHERE WE ARE CONFIDENT, AND WHERE NOT', C.warn),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 6 }, 'The 31 unverified sessions and the JOD 1,240 are arithmetic from records — certain. That the roster change caused the drop is an inference, and a weaker one: his remaining clients also booked less, which the roster change does not explain.')
      ]), { marginTop: 12 }),
      D({ display: 'flex', gap: 9, marginTop: 16, flexWrap: 'wrap' }, [
        prim('Open the 31 sessions', function () { v.openScreen('CCH-17'); }, true),
        sec('Ask Khalda to verify them', function () { v.act('flash', 'Request drafted for your approval'); }, true)
      ])
    ]);
  };

  S['ADM-SRCH-01'] = function (v) {
    var g = [['MEMBERS', [['Ahmad Nabulsi', 'Club · Khalda · owes JOD 55.00', 'ADM-MEM-01'], ['Ahmad Sabbagh', 'Flex · Khalda', 'ADM-MEM-02']]], ['ACTIONS', [['Take a payment', 'from any member record', 'ADM-PAY-04'], ['Add a member', 'walk-in join', 'ADM-MEM-10']]], ['SCREENS', [['Payments', 'the ledger', 'ADM-PAY-01'], ['Failed payment recovery', '6 waiting', 'ADM-PAY-05']]], ['ASK VEYRO', [['"why is Khalda down this month"', 'reads payments, sessions and rosters', 'ADM-AI-01']]]];
    return dPage([
      card(D({ padding: '14px 17px' }, [
        D({ display: 'flex', gap: 10, alignItems: 'center' }, [
          D({ font: '400 13px/1 ' + mono, color: C.t2 }, '⌕'),
          D({ font: '400 17px/1.3 ' + sans, flex: 1 }, 'ahmad'),
          D({ font: '400 10px/1.4 ' + mono, color: C.t2, border: '1px solid ' + C.line, padding: '2px 5px', borderRadius: 3 }, 'ESC')
        ])
      ]), { marginTop: 6, borderColor: C.ink }),
      card(g.map(function (grp, gi) {
        return D({ key: gi }, [
          D({ padding: '9px 16px', background: C.sunk, font: '500 9px/1.4 ' + mono, color: C.t2, letterSpacing: '.06em', borderTop: gi ? '1px solid ' + C.line : 'none' }, grp[0])
        ].concat(grp[1].map(function (r, i) {
          return Btn(function () { v.openScreen(r[2]); }, { display: 'flex', gap: 11, alignItems: 'center', padding: '12px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', minHeight: 44 }, [
            D({ flex: 1, minWidth: 0 }, [D({ font: '450 13px/1.4 ' + sans }, r[0]), D({ font: '400 11.5px/1.5 ' + sans, color: C.t2, marginTop: 2 }, r[1])])
          ]);
        })));
      }), { marginTop: 12 }),
      D({ font: '400 12.5px/1.65 ' + sans, color: C.t2, marginTop: 12 }, 'Only things you can actually open. Nadia searching the same word sees invoices; Layla sees no export action at all.')
    ]);
  };


  S['ADM-SET-03'] = function (v) {
    return dPage([
      h1('Tax and invoicing', 'Nadi Group · Jordan · JOD'),
      card(D({ padding: '16px 18px', maxWidth: 560 }, D({ display: 'flex', flexDirection: 'column', gap: 11 }, [
        field('Tax number', '1099238471'),
        field('Sales tax', '16% on retail · memberships exempt')
      ])), { marginTop: 14 }),
      card(D({ padding: '15px 17px', maxWidth: 560, borderColor: C.ok }, [
        D({ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }, [badge('CONNECTED', C.ok), D({ font: '500 13.5px/1.35 ' + sans, flex: 1, minWidth: 130 }, 'JoFotara e-invoicing')]),
        D({ font: '400 13px/1.7 ' + sans, color: '#2c2a26', marginTop: 8 }, 'Submitting since 14 June. 1,847 invoices sent, 3 rejected this month — all three for a missing buyer tax number, all corrected and resubmitted.'),
        D({ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }, [sec('Test the connection', function () { v.act('flash', 'Test submission accepted'); }), sec('Submission log', function () { v.openScreen('ADM-PAY-01'); })])
      ]), { marginTop: 12 }),
      card(D({ padding: '13px 15px', maxWidth: 560, background: C.sunk }, D({ font: '400 12.5px/1.65 ' + sans, color: '#2c2a26' }, 'A business sale needs the buyer\u2019s tax number. The till now requires it at the point of sale rather than failing later at submission — which is what caused this month\u2019s three rejections.')), { marginTop: 12 }),
      card(D({ padding: '13px 15px', maxWidth: 560 }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'This screen is the same shape everywhere. A UK tenant sees HMRC here instead, with different fields — nothing about it is hard-coded to Jordan except the adapter.')), { marginTop: 12 })
    ]);
  };

  S['CON-02'] = function (v) {
    var steps = [['Organisation and region', 'Done 4 days ago', C.ok], ['First administrator invited', 'Rana accepted 3 days ago', C.ok], ['Clubs and opening hours', 'Done 3 days ago', C.ok], ['Plans and pricing', 'Done 2 days ago', C.ok], ['Member import', '27 rows need a decision', C.warn], ['Payment provider', 'Not started', C.t2], ['Access hardware', 'Not started', C.t2], ['Staff accounts', 'Not started', C.t2]];
    return dPage([
      h1('Pulse Amman', 'Day 4 of onboarding · Starter · 1 club'),
      card(steps.map(function (s, i) {
        return D({ key: i, display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', borderTop: i ? '1px solid ' + C.hair : 'none', flexWrap: 'wrap' }, [
          D({ font: '400 12px/1 ' + mono, color: s[2] === C.ok ? C.ok : C.ctl, width: 14 }, s[2] === C.ok ? '☑' : '☐'),
          D({ flex: 1, minWidth: 180 }, [D({ font: '450 13.5px/1.4 ' + sans }, s[0]), D({ font: '400 11.5px/1.5 ' + sans, color: s[2] === C.warn ? C.warn : C.t2, marginTop: 2 }, s[1])]),
          s[2] === C.warn ? sec('Resolve', function () { v.openScreen('CON-05'); }) : null
        ]);
      }), { marginTop: 14 }),
      card(D({ padding: '13px 15px', maxWidth: 620, background: C.sunk }, D({ font: '400 12.5px/1.68 ' + sans, color: '#2c2a26' }, 'They can open the doors before the last three are finished — members can join and pay at the desk without access hardware. The order matters less than not being blocked.')), { marginTop: 12 })
    ]);
  };

  window.VeyroScreenIds = function () { return Object.keys(S); };

  window.VeyroScreen = function (props) {
    DARK = false; // reset per render — mPage sets it true for dark screens.
    LANG = (props.state && props.state.lang) || 'en';
    var v = props.state || {};
    var id = props.screen;
    var fn = S[id];
    if (!fn) return reference(v);
    try { return fn(v); } catch (e) { return page([D({ font: '400 13px/1.6 ' + mono, color: C.err }, 'Render error in ' + id + ': ' + (e && e.message))]); }
  };
})();
