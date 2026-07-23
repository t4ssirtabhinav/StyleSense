import {
  FlashList,
  type FlashListRef,
  type ListRenderItemInfo,
} from '@shopify/flash-list';
import { Redirect, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { View, useWindowDimensions } from 'react-native';
import { Button, Card, Text, colors } from '../../components/ui';
import { useAuthStore } from '../../features/auth/auth.store';
import { ResumePrompt } from '../../features/onboarding/components/ResumePrompt';
import { Step1BasicProfile } from '../../features/onboarding/components/Step1BasicProfile';
import { Step2StyleWardrobe } from '../../features/onboarding/components/Step2StyleWardrobe';
import { Step3OccasionPriorities } from '../../features/onboarding/components/Step3OccasionPriorities';
import { Step4BudgetColours } from '../../features/onboarding/components/Step4BudgetColours';
import { StepIndicatorDots } from '../../features/onboarding/components/StepIndicatorDots';
import {
  useCompleteOnboardingMutation,
  useOnboardingProgressQuery,
  useSaveStep1Mutation,
} from '../../features/onboarding/onboarding.queries';
import { useOnboardingStore } from '../../features/onboarding/onboarding.store';
import type {
  OnboardingStepId,
  StylePreferences,
} from '../../features/onboarding/onboarding.types';

// Replaces SS-003's disposable placeholder entirely. Per
// docs/tickets/SS-004-design.md's "Files to create/modify" #18.

export interface StepDescriptor {
  id: OnboardingStepId;
}

export const STEPS: StepDescriptor[] = [
  { id: 'basic-profile' },
  { id: 'style-wardrobe' },
  { id: 'occasion-priorities' },
  { id: 'budget-colours' },
];

const LAST_STEP_INDEX = STEPS.length - 1;

// getItemType must be set to each step's unique id so FlashList never
// attempts to recycle one step's rendered native view into another step's
// slot — see docs/tickets/SS-004-design.md's "FlashList pager" section.
// Exported as a standalone module-level function (rather than an inline
// lambda) so its 4-distinct-values regression guard can be unit-tested
// directly.
export function getStepItemType(item: StepDescriptor): OnboardingStepId {
  return item.id;
}

const STEP1_ERROR_COLOR = colors.accent.errorPlaceholder;

export default function OnboardingScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const session = useAuthStore((state) => state.session);
  const isSessionLoading = useAuthStore((state) => state.isSessionLoading);
  const userId = session?.user.id;

  const progressQuery = useOnboardingProgressQuery(userId);
  const saveStep1Mutation = useSaveStep1Mutation();
  const completeOnboardingMutation = useCompleteOnboardingMutation();

  const currentStepIndex = useOnboardingStore(
    (state) => state.currentStepIndex,
  );
  const setCurrentStepIndex = useOnboardingStore(
    (state) => state.setCurrentStepIndex,
  );
  const hydrateFromProgress = useOnboardingStore(
    (state) => state.hydrateFromProgress,
  );
  const fullName = useOnboardingStore((state) => state.fullName);
  const gender = useOnboardingStore((state) => state.gender);
  const city = useOnboardingStore((state) => state.city);
  const styleKeywords = useOnboardingStore((state) => state.styles);
  const wardrobeType = useOnboardingStore((state) => state.wardrobeType);
  const occasionsPriority = useOnboardingStore(
    (state) => state.occasionsPriority,
  );
  const budgetRange = useOnboardingStore((state) => state.budgetRange);
  const favouriteColours = useOnboardingStore(
    (state) => state.favouriteColours,
  );
  const reset = useOnboardingStore((state) => state.reset);

  const [hasDismissedResumePrompt, setHasDismissedResumePrompt] =
    useState(false);
  const [step1Error, setStep1Error] = useState<string | undefined>(undefined);

  const pagerRef = useRef<FlashListRef<StepDescriptor>>(null);
  const hasAutoHydratedRef = useRef(false);

  // Shown before Step 1 when a returning user has onboarding_completed:
  // false and already has a non-null full_name. The "routing to this screen
  // at all already implies onboarding_completed: false" precondition only
  // holds for the normal verify-otp.tsx routing path — it does NOT hold for
  // direct-URL/deep-link entry, which can land a fully-onboarded user here
  // too. The explicit !onboardingCompleted clause below covers that case —
  // see docs/tickets/SS-016-design.md.
  const showResumePrompt =
    progressQuery.isSuccess &&
    Boolean(progressQuery.data?.fullName) &&
    !progressQuery.data?.onboardingCompleted &&
    !hasDismissedResumePrompt;

  // SS-016: a completed user who reaches this screen directly (bypassing
  // ResumePrompt entirely, since showResumePrompt is false for them) would
  // otherwise see a blank Step 1 — the only other hydrate call site,
  // handleContinueSetup below, is gated behind ResumePrompt's "Continue
  // Setup" button, which this user never presses. This effect auto-hydrates
  // the store once per mount for that case only (guarded on
  // onboardingCompleted being true), so it never fires for — and can never
  // clobber — the genuinely-incomplete resume flow, which still hydrates
  // only via handleContinueSetup. See docs/tickets/SS-016-design.md.
  useEffect(() => {
    if (
      hasAutoHydratedRef.current ||
      !progressQuery.isSuccess ||
      !progressQuery.data?.onboardingCompleted
    ) {
      return;
    }
    hydrateFromProgress({
      fullName: progressQuery.data.fullName,
      gender: progressQuery.data.gender,
      city: progressQuery.data.city,
      stylePreferences: progressQuery.data.stylePreferences,
    });
    hasAutoHydratedRef.current = true;
  }, [progressQuery.isSuccess, progressQuery.data, hydrateFromProgress]);

  // Fix pass 5, 2026-07-22 (SS-004): also pass through stylePreferences
  // (already fetched by useOnboardingProgressQuery) so Steps 2-4 pre-fill
  // correctly instead of rendering blank for a user who has prior saved
  // preferences — see onboarding.store.ts's hydrateFromProgress fix.
  const handleContinueSetup = useCallback(() => {
    if (progressQuery.data) {
      hydrateFromProgress({
        fullName: progressQuery.data.fullName,
        gender: progressQuery.data.gender,
        city: progressQuery.data.city,
        stylePreferences: progressQuery.data.stylePreferences,
      });
    }
    setCurrentStepIndex(1);
    setHasDismissedResumePrompt(true);
  }, [progressQuery.data, hydrateFromProgress, setCurrentStepIndex]);

  const handleSkip = useCallback(() => {
    router.replace('/');
  }, [router]);

  const isStep1Valid =
    fullName.trim().length > 0 && Boolean(gender) && city.trim().length > 0;

  const handleNext = useCallback(() => {
    // Kept intentionally, even though the isSessionLoading/!session guard
    // above now redirects away before this screen's body (and therefore
    // this button) can ever render session-less — this is TS narrowing
    // (userId's declared type is `string | undefined`) plus a cheap
    // belt-and-suspenders guard against a future refactor reordering the
    // early-return checks above.
    if (!userId) {
      return;
    }
    if (currentStepIndex === 0) {
      if (!isStep1Valid || !gender) {
        setStep1Error(
          'Please fill in your name, gender, and city to continue.',
        );
        return;
      }
      setStep1Error(undefined);
      saveStep1Mutation.mutate(
        { userId, input: { fullName, gender, city } },
        {
          onSuccess: () => {
            const nextIndex = currentStepIndex + 1;
            setCurrentStepIndex(nextIndex);
            pagerRef.current?.scrollToIndex({
              index: nextIndex,
              animated: true,
            });
          },
          onError: () => {
            setStep1Error('Could not save your profile. Please try again.');
          },
        },
      );
      return;
    }
    const nextIndex = currentStepIndex + 1;
    setCurrentStepIndex(nextIndex);
    pagerRef.current?.scrollToIndex({ index: nextIndex, animated: true });
  }, [
    currentStepIndex,
    userId,
    isStep1Valid,
    gender,
    fullName,
    city,
    saveStep1Mutation,
    setCurrentStepIndex,
  ]);

  // Fix pass 3, 2026-07-22 (SS-004 Fix B): pure client-side/local-state
  // navigation only — all wizard answers already live in useOnboardingStore
  // (Zustand), which is never reset except by the explicit reset() call
  // after a successful "Get Started", so no re-fetch/re-save is needed on
  // Back. Mirrors handleNext's forward-navigation pattern (setCurrentStepIndex
  // + pagerRef.scrollToIndex) rather than inventing a new approach.
  const handleBack = useCallback(() => {
    if (currentStepIndex === 0) {
      return;
    }
    const prevIndex = currentStepIndex - 1;
    setCurrentStepIndex(prevIndex);
    pagerRef.current?.scrollToIndex({ index: prevIndex, animated: true });
  }, [currentStepIndex, setCurrentStepIndex]);

  const handleGetStarted = useCallback(() => {
    if (!userId || !gender) {
      return;
    }
    const stylePreferences: StylePreferences = {
      styles: styleKeywords,
      wardrobe_type: wardrobeType ?? 'equal_mix',
      occasions_priority: occasionsPriority,
      budget_range: budgetRange ?? '500_1000',
      favourite_colours: favouriteColours,
      gender,
    };
    completeOnboardingMutation.mutate(
      { userId, data: stylePreferences },
      {
        onSuccess: () => {
          reset();
          router.replace('/');
        },
      },
    );
  }, [
    userId,
    gender,
    styleKeywords,
    wardrobeType,
    occasionsPriority,
    budgetRange,
    favouriteColours,
    completeOnboardingMutation,
    reset,
    router,
  ]);

  const renderItem = useCallback(
    ({ item }: ListRenderItemInfo<StepDescriptor>) => (
      <View style={{ width }}>
        {item.id === 'basic-profile' ? <Step1BasicProfile /> : null}
        {item.id === 'style-wardrobe' ? <Step2StyleWardrobe /> : null}
        {item.id === 'occasion-priorities' ? <Step3OccasionPriorities /> : null}
        {item.id === 'budget-colours' ? <Step4BudgetColours /> : null}
      </View>
    ),
    [width],
  );

  const handleMomentumScrollEnd = useCallback(
    (event: { nativeEvent: { contentOffset: { x: number } } }) => {
      const index = Math.round(event.nativeEvent.contentOffset.x / width);
      setCurrentStepIndex(index);
    },
    [width, setCurrentStepIndex],
  );

  // (QA-blocker fix pass, 2026-07-22) `/onboarding` lives in the (auth)
  // route group, which — unlike (tabs) — has no Auth Guard, so it is
  // reachable without a session by design (e.g. a direct URL visit before
  // completing phone/OTP auth). Previously this silently rendered a wizard
  // whose "Next" button was a no-op with zero user feedback. Mirrors the
  // Auth Guard's own loading/redirect pattern (app/(tabs)/_layout.tsx) so
  // there's no one-frame flash-redirect while the initial getSession() call
  // is still in flight.
  if (isSessionLoading) {
    return (
      <Card
        testID="onboarding-session-loading"
        variant="flat"
        className="m-md flex-1 items-center justify-center"
      >
        <Text variant="body">Loading…</Text>
      </Card>
    );
  }

  if (!session) {
    return <Redirect href="/login" />;
  }

  if (showResumePrompt) {
    return (
      <ResumePrompt onContinue={handleContinueSetup} onSkip={handleSkip} />
    );
  }

  return (
    <View testID="onboarding-screen" className="flex-1">
      <View className="flex-row items-center justify-between p-md">
        <StepIndicatorDots
          currentIndex={currentStepIndex}
          total={STEPS.length}
        />
        <Button variant="ghost" onPress={handleSkip} accessibilityLabel="Skip">
          Skip
        </Button>
      </View>

      {step1Error ? (
        <Text
          variant="caption"
          style={{ color: STEP1_ERROR_COLOR }}
          className="px-md"
        >
          {step1Error}
        </Text>
      ) : null}

      <FlashList
        ref={pagerRef}
        testID="onboarding-pager"
        data={STEPS}
        renderItem={renderItem}
        getItemType={getStepItemType}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        initialScrollIndex={currentStepIndex}
        onMomentumScrollEnd={handleMomentumScrollEnd}
      />

      <View className="flex-row gap-2 p-md">
        {currentStepIndex > 0 ? (
          <Button
            variant="secondary"
            onPress={handleBack}
            accessibilityLabel="Back"
          >
            Back
          </Button>
        ) : null}
        <View className="flex-1">
          {currentStepIndex === LAST_STEP_INDEX ? (
            <Button
              onPress={handleGetStarted}
              fullWidth
              loading={completeOnboardingMutation.isPending}
            >
              Get Started
            </Button>
          ) : (
            <Button
              onPress={handleNext}
              fullWidth
              loading={saveStep1Mutation.isPending}
            >
              Next
            </Button>
          )}
        </View>
      </View>
    </View>
  );
}
