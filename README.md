# Complaints Android WebView APK

هذا مشروع Android بسيط يحول واجهة الويب إلى تطبيق APK فعلي عبر WebView.

الرابط المستخدم داخل التطبيق:
https://complaints-emergency-system.onrender.com

## البناء عبر GitHub Actions

1. ارفع هذا المجلد إلى GitHub كمستودع جديد أو داخل مستودعك الحالي.
2. افتح GitHub > Actions.
3. اختر workflow باسم Build Android APK.
4. اضغط Run workflow.
5. بعد انتهاء البناء، حمّل artifact باسم Complaints-debug-apk.

## ملاحظات

- التطبيق يطلب صلاحية الإنترنت والموقع.
- WebView يدعم JavaScript و LocalStorage و Geolocation.
- نسخة debug مناسبة للتجربة. للنشر الرسمي على Google Play نحتاج إصدار signed release.
