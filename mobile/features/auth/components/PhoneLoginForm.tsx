import { useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import { View } from 'react-native';
import {
  type AppBottomSheetRef,
  Button,
  Card,
  Input,
  Text,
} from '../../../components/ui';
import { useSendOtpMutation } from '../auth.queries';
import { validateIndianMobile } from '../auth.service';
import { CountryCodePicker } from './CountryCodePicker';

// SS-071: moved verbatim out of app/(auth)/login.tsx, which is now a
// registry host (see ../auth.methods.ts). Every string/prop/testID here is
// unchanged from before the move — AC #1 is proven by SS-003's existing
// login.test.tsx (which renders LoginScreen, and therefore this component
// through the single-entry registry) passing unmodified.

function sanitizePhoneInput(text: string): string {
  // `Input`'s phone variant enforces maxLength={10} at the RN TextInput
  // level but does not filter non-digit characters itself (confirmed by
  // reading components/ui/Input.tsx) — still admits non-digits on
  // web/paste, so this screen sanitizes before validating.
  return text.replace(/\D/g, '').slice(0, 10);
}

export function PhoneLoginForm() {
  const router = useRouter();
  const countryPickerRef = useRef<AppBottomSheetRef>(null);
  const [phone, setPhone] = useState('');
  const [error, setError] = useState<string | undefined>(undefined);
  const sendOtpMutation = useSendOtpMutation();

  const handleChangePhone = (text: string) => {
    setPhone(sanitizePhoneInput(text));
    if (error) {
      setError(undefined);
    }
  };

  const handleSendOtp = () => {
    const validation = validateIndianMobile(phone);
    if (!validation.valid) {
      setError(validation.message);
      return;
    }
    setError(undefined);
    sendOtpMutation.mutate(phone, {
      onSuccess: () => {
        router.push({ pathname: '/verify-otp', params: { phone } });
      },
      onError: (authError) => {
        setError(
          authError.message ?? 'Something went wrong. Please try again.',
        );
      },
    });
  };

  return (
    <Card
      testID="login-screen"
      variant="flat"
      className="m-md flex-1 justify-center"
    >
      <Text variant="heading" className="mb-md">
        Enter your mobile number
      </Text>
      <Input
        variant="phone"
        value={phone}
        onChangeText={handleChangePhone}
        error={error}
        onCountryCodePress={() => countryPickerRef.current?.present()}
        autoFocus
      />
      <View className="mt-md">
        <Button
          onPress={handleSendOtp}
          loading={sendOtpMutation.isPending}
          fullWidth
          accessibilityLabel="Send OTP"
        >
          Send OTP
        </Button>
      </View>
      <CountryCodePicker ref={countryPickerRef} />
    </Card>
  );
}
