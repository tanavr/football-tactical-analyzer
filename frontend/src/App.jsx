const features = [
  {
    id: 'analyze',
    number: '01',
    title: 'Analyze Team',
    description: 'Explore a team’s identity, from possession and passing to pressing and defensive activity.',
    detail: 'One club. One season. A clearer picture.',
  },
  {
    id: 'compare',
    number: '02',
    title: 'Compare Teams',
    description: 'Put two club-seasons side by side to see where their tactical approaches meet and differ.',
    detail: 'Different seasons. Shared perspective.',
  },
  {
    id: 'simulate',
    number: '03',
    title: 'Match Simulator',
    description: 'Explore a hypothetical matchup with estimated outcomes and the assumptions behind them.',
    detail: 'The match that never happened.',
  },
]

export default function App() {
  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#home" aria-label="Football Tactical Analyzer home">
          <span className="brand-mark" aria-hidden="true">FTA</span>
          <span>Football, in perspective.</span>
        </a>
        <span className="preview-label">Development preview</span>
      </header>

      <main id="home">
        <section className="hero" aria-labelledby="page-title">
          <div className="hero-copy">
            <p className="eyebrow">Beyond the scoreline</p>
            <h1 id="page-title">Football Tactical Analyzer</h1>
            <p className="subtitle">Analyze, compare, and simulate football teams across seasons.</p>
            <a className="explore-link" href="#tools">Explore the tools <span aria-hidden="true">↗</span></a>
          </div>
          <div className="pitch" aria-hidden="true">
            <div className="pitch-outline">
              <div className="halfway-line" />
              <div className="center-circle" />
              <div className="penalty-area left" />
              <div className="penalty-area right" />
              <span className="center-spot" />
            </div>
            <span className="pitch-caption">A different view of the game</span>
          </div>
        </section>

        <section className="tools" id="tools" aria-labelledby="tools-title">
          <div className="section-heading">
            <h2 id="tools-title">Three ways to read the game</h2>
            <p>The starting lineup</p>
          </div>
          <div className="feature-grid">
            {features.map((feature) => (
              <section className="feature-card" key={feature.id} aria-labelledby={`${feature.id}-title`}>
                <div className="card-top"><span className="card-number">{feature.number}</span><span className="badge">Coming soon</span></div>
                <h3 id={`${feature.id}-title`}>{feature.title}</h3>
                <p>{feature.description}</p>
                <div className="card-detail">{feature.detail}</div>
              </section>
            ))}
          </div>
          <p className="availability-note">Tools are under development. Team data, tactical scores, and simulations are not available yet.</p>
        </section>
      </main>
      <footer><span>Football Tactical Analyzer</span><span>Understand the approach. See the bigger picture.</span></footer>
    </div>
  )
}
