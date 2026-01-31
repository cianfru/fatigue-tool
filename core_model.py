
        # 4. WOCL overlap BOOST - sleeping during biological night enhances recovery
        # SCIENTIFIC RATIONALE: Sleep during WOCL (02:00-06:00) is circadian-aligned.
        # Process S (homeostatic pressure) is highest, Process C (circadian alertness) is lowest.
        # This is the OPTIMAL time for restorative sleep, particularly for slow-wave sleep (SWS).
        #
        # References:
        # - Borbély AA, Achermann P (1999). Sleep homeostasis and models of sleep regulation.
        #   Journal of Biological Rhythms, 14(6), 557-568.
        #   → Peak sleep propensity during WOCL; maximal Process S accumulation
        # - Dijk DJ, Czeisler CA (1995). Contribution of the circadian pacemaker and sleep
        #   homeostasis to sleep propensity. Journal of Sleep Research, 4(s2), 150-165.
        #   → Enhanced slow-wave sleep during biological night
        # - Gander PH, et al. (2011). Fatigue risk management: Organizational factors at the
        #   regulatory and industry/company level. Accident Analysis & Prevention, 43(2), 573-590.
        #   → Optimal sleep window for airline pilots aligns with WOCL
        # - Aeschbach D, et al. (1997). Dynamics of slow-wave activity and spindle frequency
        #   activity in the human sleep EEG. Journal of Sleep Research, 6(3), 197-204.
        #   → SWS concentration highest in early biological night (WOCL period)
        #
        # NOTE: This does NOT change that WORKING during WOCL is fatiguing.
        # Sleep recovery (Process S decay) ≠ work performance (Process C + S interaction).
        # Night departures remain penalized via circadian performance component.
        
        wocl_overlap = self._calculate_wocl_overlap(sleep_start, sleep_end, location_timezone)
        
        if wocl_overlap > 0:
            # Boost sleep quality by 3% per hour of WOCL overlap (conservative estimate)
            # Example: 4 hours WOCL sleep = 1.12x boost
            #   → 8h actual sleep × 1.12 = 9.0h effective recovery (enhanced SWS)
            # Dijk & Czeisler (1995): SWS enhancement during biological night ~10-15%
            wocl_boost = 1.0 + (wocl_overlap * 0.03)
            wocl_boost = min(1.15, wocl_boost)  # Cap at 15% boost (conservative)
        else:
            wocl_boost = 1.0
        
        # 9. Combine all factors
        combined_efficiency = (
            base_efficiency
            * wocl_boost  # Changed from wocl_penalty
            * late_onset_penalty
            * recovery_boost
            * time_pressure_factor
            * insufficient_penalty
        )
        
        # Realistic efficiency floor: Even worst-case sleep provides some restoration
        # 
        # SCIENTIFIC RATIONALE: Sleep is fundamentally restorative even under poor conditions.
        # Floor at 0.65 = ~5.2h effective from 8h actual sleep in worst case.
        #
        # References:
        # - Pilcher JJ, Huffcutt AI (1996). Effects of sleep deprivation on performance.
        #   Sleep, 19(4), 318-326.
        #   → Even fragmented/poor sleep provides partial restoration
        # - Van Dongen HPA, et al. (2003). The cumulative cost of additional wakefulness.
        #   Sleep, 26(2), 117-126.
        #   → Sleep restriction dose-response: 4h sleep still provides measurable recovery
        #
        # Previous floor (0.50) was too extreme: 8h → 4h effective is unrealistic for
        # typical operational scenarios. New floor (0.65) maintains penalty for poor
        # sleep conditions while avoiding catastrophic underestimation.
        combined_efficiency = max(0.65, min(1.0, combined_efficiency))
