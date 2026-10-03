export async function getUser(id) {
  const r = await fetch(`/api/users/${id}`, { credentials: "include" });
  return r.json();
}
