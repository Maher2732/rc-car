#include <stdio.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_twai.h"
#include "esp_twai_onchip.h"
#include "can.h"

#define RX_GPIO CONFIG_CAN_TWAI_RX_GPIO
#define ESP_bitrate CAN_BITRATE

typedef struct{//custom type to hold frame data
    uint32_t id;//message ID
    uint8_t dlc;//length of data
    uint8_t data[8];//store the data itself
}can_packet_t;

static QueueHandle_t rx_queue=NULL;

static bool twai_rx_cb(twai_node_handle_t handle, const twai_rx_done_event_data_t *edata, void *user_ctx){
    uint8_t recv_buff[8];
    twai_frame_t rx_frame={
        .buffer=recv_buff,
        .buffer_len=sizeof(recv_buff),
    };
    if(ESP_OK==twai_node_receive_from_isr(handle,&rx_frame)){
        can_packet_t packet={
            .id=rx_frame.header.id,
            .dlc=rx_frame.header.dlc,
        };

        if(packet.dlc>8){
            packet.dlc=8;
        }

        for(int i=0;i<packet.dlc;i++){//copying the frame array to your typedef
            packet.data[i]=recv_buff[i];
        }
        BaseType_t high_task_wakeup=pdFALSE;//send to queue
        if(xQueueSendFromISR(rx_queue,&packet,&high_task_wakeup)!=pdTRUE){
            return false;
        }//bc its ISR you need to use fromISR
        return high_task_wakeup==pdTRUE;
    }
    return false;
}

void can_receiver_run(void){
    twai_node_handle_t listener_node=NULL;
    twai_onchip_node_config_t listener_config={
        .io_cfg={
            .tx=-1,
            .rx=RX_GPIO,
        },
        .bit_timing.bitrate=ESP_bitrate,
        .flags.enable_listen_only=true,
    };
    ESP_ERROR_CHECK(twai_new_node_onchip(&listener_config,&listener_node));
    rx_queue=xQueueCreate(10,sizeof(can_packet_t));//sets the queue, 10 packet Q
    if(rx_queue==NULL){
        printf("Failed to create RX queue\n");
        return;
    }
    twai_event_callbacks_t user_cbs={
        .on_rx_done=twai_rx_cb,
    };
    ESP_ERROR_CHECK(twai_node_register_event_callbacks(listener_node,&user_cbs,NULL));
    ESP_ERROR_CHECK(twai_node_enable(listener_node));
    while (1) {
        can_packet_t packet;
        if(xQueueReceive(rx_queue,&packet,portMAX_DELAY)==pdTRUE){
            printf("Message received\n");
            printf("ID: 0x%" PRIX32 "\n",packet.id);
            printf("DLC: %d\n",packet.dlc);

            printf("Data: ");
            for(int i=0;i<packet.dlc;i++){
                printf("%02X ",packet.data[i]);//print as hex, use upper case and always show 2 digits
            }
            printf("\n\n");
        }
    }
}
