/** The app has two pages, "/" and "/games/:id", so a few lines replace a router library. */
export const route = $state({ path: location.pathname })

export function navigate(path: string): void {
  history.pushState(null, '', path)
  route.path = path
}

window.addEventListener('popstate', () => {
  route.path = location.pathname
})
