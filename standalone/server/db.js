export function database(env) {
  if (!env.DB?.prepare) throw new Error('Study database is unavailable.');
  return env.DB;
}
export async function readSession(db, id) {
  return db.prepare('SELECT * FROM study_sessions WHERE participant_id = ?').bind(id).first();
}
export async function readResponses(db, id) {
  return (await db.prepare('SELECT * FROM study_responses WHERE participant_id = ? ORDER BY trial_order').bind(id).all()).results;
}
