export function flashButton(id: string) {
  if (typeof document === "undefined") return;
  const el = document.getElementById(id);
  if (!el) return;

  el.classList.remove("btn-flash");
  (el as HTMLElement).offsetHeight; // trigger reflow
  el.classList.add("btn-flash");

  window.setTimeout(() => el.classList.remove("btn-flash"), 650);
}
