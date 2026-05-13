-- ============================================================
-- DR. WARIS ANWAR AESTHETICS - SUPABASE DATABASE SETUP
-- Run this in Supabase SQL Editor (supabase.com > SQL Editor)
-- ============================================================

-- 1. CONVERSATIONS TABLE
CREATE TABLE IF NOT EXISTS conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_phone TEXT NOT NULL,
    customer_name TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'closed', 'pending')),
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    unread_count INTEGER DEFAULT 0
);

CREATE INDEX idx_conversations_phone ON conversations(customer_phone);
CREATE INDEX idx_conversations_last_msg ON conversations(last_message_at DESC);

-- 2. MESSAGES TABLE
CREATE TABLE IF NOT EXISTS messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL CHECK (sender_type IN ('customer', 'ai_agent', 'human_agent')),
    message_text TEXT NOT NULL,
    message_type TEXT DEFAULT 'text' CHECK (message_type IN ('text', 'image', 'audio')),
    whatsapp_message_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conv ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at DESC);

-- 3. APPOINTMENTS TABLE
CREATE TABLE IF NOT EXISTS appointments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    service TEXT NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    status TEXT DEFAULT 'confirmed' CHECK (status IN ('pending', 'confirmed', 'completed', 'cancelled', 'no_show')),
    notes TEXT,
    google_event_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_appointments_date ON appointments(appointment_date);
CREATE INDEX idx_appointments_phone ON appointments(customer_phone);
CREATE INDEX idx_appointments_status ON appointments(status);

-- 4. FUNCTION TO INCREMENT UNREAD COUNT
CREATE OR REPLACE FUNCTION increment_unread(conv_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE conversations 
    SET unread_count = unread_count + 1 
    WHERE id = conv_id;
END;
$$ LANGUAGE plpgsql;

-- 5. ENABLE REALTIME
ALTER PUBLICATION supabase_realtime ADD TABLE conversations;
ALTER PUBLICATION supabase_realtime ADD TABLE messages;
ALTER PUBLICATION supabase_realtime ADD TABLE appointments;

-- 6. ROW LEVEL SECURITY (basic - allow all for authenticated)
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated" ON conversations FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for authenticated" ON messages FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for authenticated" ON appointments FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- Allow service role (for edge functions / backend)
CREATE POLICY "Allow all for service role" ON conversations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for service role" ON messages FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for service role" ON appointments FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================
-- DONE! Database is ready.
-- ============================================================
