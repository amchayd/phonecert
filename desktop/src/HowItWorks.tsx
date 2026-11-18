/** A plain explanation of what the app does, in the order a buyer uses it. Static text, no data. */
const STEPS: { title: string; where: string; text: string }[] = [
  { title: "Connect and scan", where: "Scan",
    text: "Plug the iPhone in over USB, unlock it and tap Trust This Computer. The scan takes about twenty seconds and only reads: identity, battery gauge, storage, crash logs, installed apps and the serials of the parts. Nothing is installed on the phone." },
  { title: "Read the verdict", where: "Trust",
    text: "The deal-breakers first: Find My (Activation Lock), blacklist, company management, carrier lock, jailbreak hints and unknown parts. Red means do not buy as it is, amber means ask the seller, grey means not checked yet." },
  { title: "Look at the details", where: "Device, Battery, Parts, System",
    text: "Battery health, cycles and internal resistance; whether the battery passes Apple's authentication, the Face ID self-test, and whether the display, cameras and Taptic Engine were built before the logic board (a later date means the part was fitted afterwards); kernel panics and other crash counts." },
  { title: "Test the hardware", where: "Tests",
    text: "Start tests shows a QR code. Open it in Safari on the phone, on the same Wi-Fi as this Mac. The page tests touch, display, speakers, microphone, cameras, motion sensors, GPS and Wi-Fi speed, and sends each result back here." },
  { title: "Check by hand", where: "Checklist",
    text: "What no software can see: buttons and switches, Face ID, True Tone, a real call, Bluetooth, Apple Pay, the liquid indicator in the SIM tray, and the body and glass. You mark each one pass or fail." },
  { title: "Come back later", where: "History",
    text: "Every scan is saved on this Mac with its test results. Open one to review it, finish the tests or run the paid checks." },
];

export function HowItWorks() {
  return (
    <section className="page" data-testid="how-it-works">
      <header className="page-head">
        <h1>How it works</h1>
        <p className="lead">PhoneCert checks a used iPhone before you buy or resell it: what the phone reports about itself over the cable, what its hardware does in a browser test, and what you confirm by hand.</p>
      </header>

      <ol className="how-steps">
        {STEPS.map((s) => (
          <li key={s.title}>
            <div className="how-title">{s.title} <span className="muted small">{s.where}</span></div>
            <div>{s.text}</div>
          </li>
        ))}
      </ol>

      <section className="block">
        <header className="block-head"><h3>What costs money</h3></header>
        <p>Scanning and testing are free. Only the blacklist and carrier-lock lookup is paid: it asks an outside provider about the phone's IMEI, costs a few cents, and runs only when you press Run check on the Trust page. It needs a provider key, added in Settings.</p>
      </section>

      <section className="block">
        <header className="block-head"><h3>Where the data goes</h3></header>
        <p>Everything stays on this Mac, as files in the PhoneCert reports folder. The one exception is the paid lookup, which sends the IMEI to the provider you chose. The test page is served by this Mac to the phone over your own Wi-Fi, protected by a one-time code.</p>
      </section>

      <section className="block">
        <header className="block-head"><h3>What it cannot tell you</h3></header>
        <ul>
          <li>Apple's own Parts and Service History is not readable over the cable. Check it on the phone: Settings, General, About.</li>
          <li>Newer iPhones use random serials, so part build dates cannot be compared on them.</li>
          <li>Some limits are first estimates from few phones, such as the internal resistance limit. They are marked provisional.</li>
          <li>A clean result lowers the risk; it is not a guarantee. A phone can be reported stolen after you bought it.</li>
        </ul>
      </section>
    </section>
  );
}
