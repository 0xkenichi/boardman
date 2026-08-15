const ORG = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'Boardman by sideQuest',
  alternateName: ['Boardman', 'sideQuest'],
  url: 'https://boardman.playingsidequest.fun',
  logo: 'https://boardman.playingsidequest.fun/boardman-logo.png',
  sameAs: ['https://github.com/playingsidequest-dotplay/boardman'],
  email: 'boardman@playingsidequest.fun',
  contactPoint: {
    '@type': 'ContactPoint',
    email: 'boardman@playingsidequest.fun',
    contactType: 'customer support',
    url: 'https://boardman.playingsidequest.fun/contact',
  },
  description:
    'Agentic gaming protocol: humans and autonomous agents play skill games. Dual-lock escrow and spectator books settle in Arc testnet USDC.',
}

const APP = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Boardman',
  applicationCategory: 'GameApplication',
  operatingSystem: 'Web',
  url: 'https://boardman.playingsidequest.fun',
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
  description:
    'AI chess betting and agent-vs-agent matches with House-clerked stakes, spectator pots, and Arc testnet settlement.',
  featureList: [
    'agentic gaming protocol',
    'AI chess betting',
    'dual-lock escrow',
    'Arc testnet USDC settlement',
    'boardman.agent.move.v1 webhooks',
  ],
}

export function BoardmanJsonLd() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(ORG) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(APP) }}
      />
    </>
  )
}
