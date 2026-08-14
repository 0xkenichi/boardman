import dynamic from 'next/dynamic'

const BoardmanDeskScene = dynamic(() => import('@/components/rematch/BoardmanDeskScene'), {
  ssr: false,
})

export default function RematchAppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="bm-app">
      <div className="bm-app-stage" aria-hidden>
        <BoardmanDeskScene />
        <div className="bm-app-veil" />
      </div>
      <div className="bm-app-body">{children}</div>
    </div>
  )
}
