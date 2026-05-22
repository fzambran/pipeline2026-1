-- Titanic passengers table
-- Integrity constraints mirror the semantic rules in src/validate.py

CREATE TABLE IF NOT EXISTS passengers (
    passenger_id   INTEGER      PRIMARY KEY,
    age            NUMERIC(5,2) NOT NULL,
    fare           NUMERIC(10,4) NOT NULL,
    sex            VARCHAR(10)  NOT NULL,
    sibsp          SMALLINT     NOT NULL,
    parch          SMALLINT     NOT NULL,
    pclass         SMALLINT     NOT NULL,
    embarked       CHAR(1),
    survived       SMALLINT     NOT NULL,
    family_size    SMALLINT     NOT NULL,
    is_alone       SMALLINT     NOT NULL,
    fare_per_person NUMERIC(10,4),
    age_group      VARCHAR(10),
    loaded_at      TIMESTAMP    NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_sex          CHECK (sex IN ('male', 'female')),
    CONSTRAINT chk_pclass       CHECK (pclass IN (1, 2, 3)),
    CONSTRAINT chk_survived     CHECK (survived IN (0, 1)),
    CONSTRAINT chk_embarked     CHECK (embarked IN ('S', 'C', 'Q')),
    CONSTRAINT chk_age          CHECK (age >= 0 AND age <= 120),
    CONSTRAINT chk_fare         CHECK (fare >= 0),
    CONSTRAINT chk_family_size  CHECK (family_size >= 1),
    CONSTRAINT chk_is_alone     CHECK (is_alone IN (0, 1))
);
