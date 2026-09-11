import { sql } from 'drizzle-orm';
import { sqliteTable, text, integer, real, primaryKey, foreignKey, uniqueIndex, index, check } from 'drizzle-orm/sqlite-core';

export const sessions = sqliteTable('study_sessions', {
  participantId: text('participant_id').primaryKey(),
  nickname: text('nickname').notNull().default(''),
  ratingScale: text('rating_scale').notNull().default('va-0.05_match-1_naturalness-1_v1'),
  tokenHash: text('token_hash').notNull(),
  studyVersion: text('study_version').notNull(),
  collectionVersion: text('collection_version').notNull(),
  recordType: text('record_type').notNull(),
  groupNumber: integer('group_number').notNull(),
  seed: integer('seed').notNull(),
  comfortableEnglish: integer('comfortable_english').notNull(),
  headphones: integer('headphones').notNull(),
  previouslyUsedStudio: integer('previously_used_studio').notNull(),
  consentUtc: text('consent_utc').notNull(),
  receivedUtc: text('received_utc').notNull(),
  updatedUtc: text('updated_utc').notNull(),
  completedUtc: text('completed_utc'),
  withdrawnUtc: text('withdrawn_utc'),
}, t => [
  index('idx_sessions_type_group').on(t.recordType, t.groupNumber),
  check('session_type', sql`${t.recordType} IN ('human_response', 'technical_test')`),
  check('session_group', sql`${t.groupNumber} BETWEEN 1 AND 16`),
  check('session_seed', sql`${t.seed} BETWEEN 0 AND 4294967295`),
]);

export const responses = sqliteTable('study_responses', {
  participantId: text('participant_id').notNull().references(() => sessions.participantId, { onDelete: 'cascade' }),
  trialOrder: integer('trial_order').notNull(),
  itemId: text('item_id').notNull(),
  blockId: text('block_id').notNull(),
  valence: real('valence').notNull(),
  arousal: real('arousal').notNull(),
  naturalness: integer('naturalness').notNull(),
  targetMatch: real('target_match'),
  playCount: integer('play_count').notNull(),
  completedAudio: integer('completed_audio').notNull(),
  elapsedSeconds: real('elapsed_s').notNull(),
  createdUtc: text('created_utc').notNull(),
  receivedUtc: text('received_utc').notNull(),
  completedUtc: text('completed_utc'),
}, t => [
  primaryKey({ columns: [t.participantId, t.trialOrder] }),
  uniqueIndex('idx_response_session_item').on(t.participantId, t.itemId),
  check('response_order', sql`${t.trialOrder} BETWEEN 1 AND 45`),
  check('response_valence', sql`${t.valence} BETWEEN -1 AND 1`),
  check('response_arousal', sql`${t.arousal} BETWEEN -1 AND 1`),
  check('response_naturalness', sql`${t.naturalness} BETWEEN 1 AND 5`),
  check('response_target_match', sql`${t.targetMatch} IS NULL OR ${t.targetMatch} BETWEEN 1 AND 5`),
]);

export const interactiveSessions = sqliteTable('interactive_sessions', {
 sessionId:text('session_id').primaryKey(), tokenHash:text('token_hash').notNull(), nickname:text('nickname').notNull(), mode:text('mode').notNull(), engine:text('engine'), recordType:text('record_type').notNull(), version:text('version').notNull(), consentUtc:text('consent_utc').notNull(), receivedUtc:text('received_utc').notNull(), updatedUtc:text('updated_utc').notNull(), withdrawnUtc:text('withdrawn_utc')
}, t=>[index('idx_interactive_sessions_updated').on(t.updatedUtc),check('interactive_mode',sql`${t.mode} IN ('line','explore')`),check('interactive_engine',sql`${t.engine} IS NULL OR ${t.engine} IN ('pyttsx3','sapi5xml','espeak','kokoro','chatterbox','zipvoice','styletts2','cosyvoice2','parlertts','piper')`),check('interactive_type',sql`${t.recordType} IN ('interactive_exploration','technical_test')`),check('interactive_engine_mode',sql`(${t.mode}='explore' AND ${t.engine} IS NOT NULL) OR (${t.mode}='line' AND ${t.engine} IS NULL)`)]);
export const interactiveTurns = sqliteTable('interactive_turns', {
 sessionId:text('session_id').notNull().references(()=>interactiveSessions.sessionId,{onDelete:'cascade'}), turnOrder:integer('turn_order').notNull(), engine:text('engine').notNull(), emotion:text('emotion').notNull(), inputText:text('input_text').notNull(), outputText:text('output_text').notNull(), turnJson:text('turn_json').notNull(), createdUtc:text('created_utc').notNull(), receivedUtc:text('received_utc').notNull()
},t=>[primaryKey({columns:[t.sessionId,t.turnOrder]}),check('interactive_order',sql`${t.turnOrder} BETWEEN 1 AND 100`),check('interactive_turn_engine',sql`${t.engine} IN ('pyttsx3','sapi5xml','espeak','kokoro','chatterbox','zipvoice','styletts2','cosyvoice2','parlertts','piper')`),check('interactive_emotion',sql`${t.emotion} IN ('happy','upset','sad','calm')`)]);

export const interactiveRatings = sqliteTable('interactive_ratings', {
 sessionId:text('session_id').notNull(),turnOrder:integer('turn_order').notNull(),valence:real('valence').notNull(),arousal:real('arousal').notNull(),naturalness:integer('naturalness').notNull(),targetMatch:real('target_match').notNull(),ratingScale:text('rating_scale').notNull(),ratingJson:text('rating_json').notNull(),createdUtc:text('created_utc').notNull(),receivedUtc:text('received_utc').notNull()
},t=>[primaryKey({columns:[t.sessionId,t.turnOrder]}),foreignKey({columns:[t.sessionId,t.turnOrder],foreignColumns:[interactiveTurns.sessionId,interactiveTurns.turnOrder]}).onDelete('cascade'),check('message_valence',sql`${t.valence} BETWEEN -1 AND 1`),check('message_arousal',sql`${t.arousal} BETWEEN -1 AND 1`),check('message_naturalness',sql`${t.naturalness} BETWEEN 1 AND 5`),check('message_match',sql`${t.targetMatch} BETWEEN 1 AND 5`)]);

export const interactiveAudio = sqliteTable('interactive_audio', {
 sessionId:text('session_id').notNull(),turnOrder:integer('turn_order').notNull(),sha256:text('sha256').notNull(),objectKey:text('object_key').notNull(),byteLength:integer('byte_length').notNull(),sampleRate:integer('sample_rate').notNull(),durationSeconds:real('duration_s').notNull(),storedUtc:text('stored_utc').notNull()
},t=>[primaryKey({columns:[t.sessionId,t.turnOrder]}),foreignKey({columns:[t.sessionId,t.turnOrder],foreignColumns:[interactiveTurns.sessionId,interactiveTurns.turnOrder]}).onDelete('cascade')]);

export const generationAttempts=sqliteTable('generation_attempts',{
 sessionId:text('session_id').notNull().references(()=>interactiveSessions.sessionId,{onDelete:'cascade'}),
 attemptId:text('attempt_id').notNull(),eventJson:text('event_json').notNull(),receivedUtc:text('received_utc').notNull()
},t=>[primaryKey({columns:[t.sessionId,t.attemptId]})]);
