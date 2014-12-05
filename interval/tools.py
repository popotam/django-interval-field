def cmp_relativedeltas(lhs, rhs):
    return cmp(
        (
            lhs.years, lhs.months, lhs.days, lhs.hours,
            lhs.minutes, lhs.seconds, lhs.microseconds,
        ),
        (
            rhs.years, rhs.months, rhs.days, rhs.hours,
            rhs.minutes, rhs.seconds, rhs.microseconds,
        ),
    )
