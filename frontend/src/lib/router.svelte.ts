export const route = $state({ path: location.pathname })

export function navigate(path: string): void {
  history.pushState(null, '', path)
  route.path = path
}

window.addEventListener('popstate', () => {
  route.path = location.pathname
})

document.addEventListener('click', (e) => {
  const link = (e.target as Element).closest('a[href^="/"]')
  if (link instanceof HTMLAnchorElement && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
    e.preventDefault()
    navigate(link.pathname)
  }
})
