import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, View } from 'react-native';
import { Button, Card, Input, Text } from '../../components/ui';
import {
  useOnboardingCompletedQuery,
  useSendOtpMutation,
  useVerifyOtpMutation,
} from '../../features/auth/auth.queries';
import { useSmsAutoRead } from '../../hooks/useSmsAutoRead';

const RESEND_COOLDOWN_SECONDS = 30;
const GENERIC_OTP_ERROR_MESSAGE =
  'Incorrect or expired OTP. Please try again or resend.';

export default function VerifyOtpScreen() {
  const router = useRouter();
  const { phone: phoneParam } = useLocalSearchParams<{ phone: string }>();
  const phone = phoneParam ?? '';

  const [otp, setOtp] = useState('');
  const [otpError, setOtpError] = useState<string | undefined>(undefined);
  const [secondsRemaining, setSecondsRemaining] = useState(
    RESEND_COOLDOWN_SECONDS,
  );
  const [verifiedUserId, setVerifiedUserId] = useState<string | undefined>(
    undefined,
  );

  const sendOtpMutation = useSendOtpMutation();
  const verifyOtpMutation = useVerifyOtpMutation();
  const onboardingCompletedQuery = useOnboardingCompletedQuery(verifiedUserId);

  // Android SMS auto-read: a documented no-op stub on this pass (BL-019) —
  // manual typing, paste-fill, and auto-submit all work today without it.
  useSmsAutoRead(setOtp);

  // Resend cooldown: a legitimate timer side effect (not "derived state" in
  // the sense CLAUDE.md's anti-pattern rule guards against) — there is no
  // prop/state this value could instead be computed from during render.
  // A single interval is created once on mount and left running; pressing
  // "Resend" only resets the counter it decrements, not the interval itself.
  useEffect(() => {
    const interval = setInterval(() => {
      setSecondsRemaining((seconds) => (seconds > 0 ? seconds - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Post-verify navigation decision: a real side effect (imperative
  // navigation once the profile-exists query settles), not derived state.
  useEffect(() => {
    if (!verifiedUserId || !onboardingCompletedQuery.isSuccess) {
      return;
    }
    router.replace(onboardingCompletedQuery.data ? '/' : '/onboarding');
  }, [
    verifiedUserId,
    onboardingCompletedQuery.isSuccess,
    onboardingCompletedQuery.data,
    router,
  ]);

  const handleVerify = (code: string) => {
    setOtpError(undefined);
    verifyOtpMutation.mutate(
      { phone, token: code },
      {
        onSuccess: (session) => {
          setVerifiedUserId(session.user.id);
        },
        onError: (authError) => {
          setOtpError(authError.message ?? GENERIC_OTP_ERROR_MESSAGE);
        },
      },
    );
  };

  const handleResend = () => {
    setSecondsRemaining(RESEND_COOLDOWN_SECONDS);
    sendOtpMutation.mutate(phone);
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={{ flex: 1 }}
    >
      <Card
        testID="verify-otp-screen"
        variant="flat"
        className="m-md flex-1 justify-center"
      >
        <Text variant="heading" className="mb-md">
          {`OTP sent to +91 ${phone}`}
        </Text>
        <Input
          variant="otp"
          value={otp}
          onChangeText={setOtp}
          error={otpError}
          onComplete={handleVerify}
          autoFocus
        />
        <Text variant="caption" color="muted" className="mt-sm">
          Didn't receive the SMS? Check if DND is active on your number.
        </Text>
        <View className="mt-md">
          <Button
            variant="ghost"
            onPress={handleResend}
            disabled={secondsRemaining > 0}
            accessibilityLabel="Resend OTP"
          >
            {secondsRemaining > 0
              ? `Resend OTP (${secondsRemaining}s)`
              : 'Resend OTP'}
          </Button>
        </View>
      </Card>
    </KeyboardAvoidingView>
  );
}
