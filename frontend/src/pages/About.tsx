import Nav from '../components/Nav'

export default function About() {
  return (
    <div className="about-page">
      <Nav />
      <div className="about-content">
        <h1 className="about-heading">About ClauseGuard</h1>

        <section className="about-section">
          <p className="about-body">
            ClauseGuard is a tool that reads leases and contracts so you don't have to decode them alone.
            Upload any PDF lease, rental agreement, employment contract, or NDA. We extract every clause,
            explain it in plain English, flag the risks, and tell you exactly what to do about each one.
          </p>
          <p className="about-body">
            We built ClauseGuard because most people sign legal documents they don't fully understand.
            Landlords and employers use dense legal language that creates real obligations. Buried inside
            standard-looking documents are clauses that can cost you thousands of dollars or your security deposit.
            ClauseGuard surfaces those clauses instantly.
          </p>
        </section>

        <section className="about-section">
          <h2 className="about-subheading">What we analyze</h2>
          <div className="about-grid">
            {[
              'Residential leases',
              'Commercial leases',
              'Employment contracts',
              'NDAs',
              'Service agreements',
              'Purchase agreements',
              'Roommate agreements',
              'Sublease agreements',
            ].map(item => (
              <div key={item} className="about-grid-item">{item}</div>
            ))}
          </div>
        </section>

        <section className="about-section">
          <h2 className="about-subheading">How it works</h2>
          <div className="about-steps">
            {[
              { n: '01', title: 'PDF parsing', body: 'We use pdfplumber to extract the full text of your document, preserving structure and paragraph order.' },
              { n: '02', title: 'Clause segmentation', body: 'A two-pass algorithm splits the document into individual clauses using section headers, numbered items, and keyword patterns.' },
              { n: '03', title: 'AI analysis', body: 'All clauses are sent in a single batched call to Llama 3.1 70B via Groq. The model explains each clause, assigns a risk level, and writes a plain-English verdict.' },
              { n: '04', title: 'Scoring', body: 'A safety score (0-100) is computed: each high-risk clause deducts 20 points, medium deducts 8, favorable adds 5.' },
            ].map(step => (
              <div key={step.n} className="about-step">
                <div className="about-step-num">{step.n}</div>
                <div>
                  <div className="about-step-title">{step.title}</div>
                  <p className="about-body">{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="about-section">
          <h2 className="about-subheading">Privacy</h2>
          <p className="about-body">
            Your PDF is never written to disk. It is processed in memory, and the file itself is discarded
            as soon as the text has been read. We do not log document contents, and no account is required.
          </p>
          <p className="about-body">
            To avoid re-running an analysis you have already paid for in waiting time, the finished analysis
            (not the PDF) is held in memory on the server for 15 minutes, keyed by a hash of the file. It is
            capped at a couple of dozen documents, never written to disk, and cleared whenever the server restarts.
          </p>
          <p className="about-body">
            Your analysis history is saved in your own browser so it survives a refresh. It never leaves your
            device, and you can delete it at any time with the Clear history button on the History page.
          </p>
          <p className="about-body">
            The action buttons at the bottom of a result (Draft appeal letter, Questions to ask, and the others)
            open claude.ai in a new tab with the relevant clause text included in the link, so that text is sent
            to Anthropic when you click one. Nothing is sent unless you choose to click.
          </p>
        </section>

        <section className="about-section">
          <h2 className="about-subheading">Legal disclaimer</h2>
          <p className="about-body about-disclaimer">
            ClauseGuard is not a law firm and does not provide legal advice. The analysis provided is for
            informational and educational purposes only. Nothing here constitutes legal advice, and you should
            consult a qualified attorney before making any legal decisions. ClauseGuard makes no warranties
            about the accuracy or completeness of any analysis.
          </p>
        </section>
      </div>
    </div>
  )
}
